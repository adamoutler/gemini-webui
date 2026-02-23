pipeline {
    agent {
        label 'aitop'
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
                    echo "Deployment Started: $(date)" >> deployment.log
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
        
        stage('Deploy Gemini WebUI') {
            steps {
                script {
                    // Generate a stable key for this deployment
                    env.SECRET_KEY = java.util.UUID.randomUUID().toString()
                    env.ALLOWED_ORIGINS = "https://gemini.hackedyour.info"

                    withCredentials([
                        string(credentialsId: 'GOOGLE_API_KEY', variable: 'GEMINI_API_KEY'),
                        usernamePassword(credentialsId: 'ldap-bind-auth-user', passwordVariable: 'AD_BIND_PASS', usernameVariable: 'AD_BIND_USER_DN')
                    ]) {
                        sh 'docker pull python:3.11-slim'
                        sh 'docker buildx build --load -t gemini-webui .'
                        sh 'docker compose down --remove-orphans || true'
                        sh 'docker compose up -d --force-recreate'
                    }
                }
            }
        }
    }
    
    post {
        always {
            sh 'docker compose ps'
            script {
                env.BUILD_RESULT = currentBuild.currentResult
            }
            withCredentials([string(credentialsId: 'Adam-Jenkins-Token', variable: 'ADAM_TOKEN')]) {
                sh '''
                    curl -sL -u "adamoutler@gmail.com:$ADAM_TOKEN" "${BUILD_URL}consoleText" > /tmp/jenkins-receipt-gemini-webui.log
                    echo "Finished: $BUILD_RESULT #$BUILD_NUMBER" >> /tmp/jenkins-receipt-gemini-webui.log
                '''
            }
        }
    }
}