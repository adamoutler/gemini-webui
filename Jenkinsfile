pipeline {
    agent {
        label 'aitop'
    }

    environment {
        LDAP_SERVER = 'ldaps://192.168.1.100'
        LDAP_BASE_DN = 'CN=Users,DC=activedirectory,DC=adamoutler,DC=com'
        LDAP_AUTHORIZED_GROUP = 'CN=gemini-webui,OU=Groups,dc=activedirectory,dc=adamoutler,dc=com'
        ALLOWED_ORIGINS = '*'
    }

    options {
        disableConcurrentBuilds()
    }

    stages {
        stage('Initialize Build') {
            steps {
                // Initialize the deployment log and signal start
                sh '''
                    echo "--- DEPLOYMENT STARTING #$BUILD_NUMBER ---" > deployment.log
                    echo "Build Number: $BUILD_NUMBER" >> deployment.log
                    echo "Gemini WebUI Build Started: $(date)" >> deployment.log
                    cp deployment.log /tmp/jenkins-receipt-gemini-webui.log
                    sync
                '''
            }
        }
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Image') {
            steps {
                sh 'docker pull python:3.11-slim'
                // Ensure a local directory exists for buildx caching
                sh 'mkdir -p /tmp/.buildx-cache'

                // Use buildx with local cache targets
                sh """
                docker buildx build \\
                    --load \\
                    --cache-from=type=local,src=/tmp/.buildx-cache \\
                    --cache-to=type=local,dest=/tmp/.buildx-cache-new,mode=max \\
                    -t gemini-webui:${BUILD_NUMBER} .
                """

                // Rotate the cache to prevent it from growing indefinitely
                sh "rm -rf /tmp/.buildx-cache && mv /tmp/.buildx-cache-new /tmp/.buildx-cache"
            }
        }

        stage('Parallel Tests') {
            parallel {
                stage('Lint & NPM') {
                    steps {
                        sh '''
                            # Setup python env for pre-commit
                            python3 -m venv .venv
                            . .venv/bin/activate
                            pip install pre-commit
                            pre-commit run --all-files

                            # Run NPM tests if package.json has a test script
                            npm install || true
                            npm run test --if-present || true
                        '''
                    }
                }
                stage('Unit Tests') {
                    steps {
                        sh '''
                            # Setup virtual environment and install dependencies
                            ./setup_dev.sh
                            # Generate JUnit XML for sound evidence
                            PYTHONPATH=. .venv/bin/pytest -s tests/unit/ --junitxml=unit-results.xml
                        '''
                    }
                    post {
                        always {
                            junit 'unit-results.xml'
                        }
                    }
                }
                stage('E2E Tests') {
                    steps {
                        sh '''
                            # Setup virtual environment and install dependencies
                            ./setup_dev.sh
                            .venv/bin/playwright install-deps
                            # Generate JUnit XML for sound evidence
                            PYTHONPATH=. timeout 15m .venv/bin/pytest -s tests/e2e/ --junitxml=e2e-results.xml
                        '''
                    }
                    post {
                        always {
                            junit 'e2e-results.xml'
                        }
                    }
                }
            }
        }

        stage('Deploy Gemini WebUI') {
            steps {
                script {
                    withCredentials([
                        usernamePassword(credentialsId: 'ldap-bind-auth-user', passwordVariable: 'LDAP_BIND_PASS', usernameVariable: 'LDAP_BIND_USER_DN')
                    ]) {
                        sh "sed -i 's/\\\${USERNAME}/jenkins/g' .gemini/GEMINI.md || true"
                        // Tag the already built image for deployment
                        sh "docker tag gemini-webui:${BUILD_NUMBER} gemini-webui:latest"
                        sh 'docker compose down --remove-orphans || true'
                        sh 'docker compose up -d --force-recreate'
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                env.BUILD_RESULT = currentBuild.currentResult
            }
            withCredentials([
                string(credentialsId: 'Adam-Jenkins-Token', variable: 'ADAM_TOKEN'),
                usernamePassword(credentialsId: 'ldap-bind-auth-user', passwordVariable: 'LDAP_BIND_PASS', usernameVariable: 'LDAP_BIND_USER_DN')
            ]) {
                sh 'docker compose ps'
                sh '''
                    echo "--- FINALIZING LOGS ---" >> /tmp/jenkins-receipt-gemini-webui.log
                    curl -sL -u "adamoutler@gmail.com:$ADAM_TOKEN" "${BUILD_URL}consoleText" >> /tmp/jenkins-receipt-gemini-webui.log
                    echo "This is the absolute, and final, build result for the code you just pushed to the repository." >> /tmp/jenkins-receipt-gemini-webui.log
                    echo "Gemini WebUI Build Finished: $BUILD_RESULT #$BUILD_NUMBER" >> /tmp/jenkins-receipt-gemini-webui.log
                    if [ "$BUILD_RESULT" != "SUCCESS" ]; then
                        echo "You have committed faulty code. Fix it and recommit, then git p to validate. " >> /tmp/jenkins-receipt-gemini-webui.log
                    fi
                '''
            }
        }
    }
}
