pipeline {
    agent {
        label 'aitop'
    }

    environment {
        LDAP_SERVER = 'ldaps://192.168.1.100'
        LDAP_BASE_DN = 'CN=Users,DC=activedirectory,DC=adamoutler,DC=com'
        LDAP_AUTHORIZED_GROUP = 'CN=gemini-webui,OU=Groups,dc=activedirectory,dc=adamoutler,dc=com'
        ALLOWED_ORIGINS = 'https://gemini.hackedyour.info'
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

        stage('Lint') {
            steps {
                sh '''
                    ./setup_dev.sh
                    .venv/bin/pre-commit run --all-files
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    # Setup virtual environment and install dependencies
                    ./setup_dev.sh
                    # Generate JUnit XML for sound evidence
                    PYTHONPATH=. .venv/bin/pytest -s tests/ --junitxml=results.xml
                '''
            }
            post {
                always {
                    junit 'results.xml'
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
                        sh 'docker pull python:3.11-slim'
                        sh "docker buildx build --load -t gemini-webui ."
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
                    test "$BUILD_RESULT" != "SUCCESS" && echo "You have committed faulty code. Fix it and recommit, then git p to validate. " >> /tmp/jenkins-receipt-gemini-webui.log
                '''
            }
        }
    }
}
