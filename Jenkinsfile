pipeline {
    agent {
        label 'aitop'
    }
    
    stages {
        stage('Initialize Build') {
            steps {
                // Initialize the deployment log and signal start
                sh """
                    echo '--- DEPLOYMENT STARTING #${env.BUILD_NUMBER} ---' > deployment.log
                    echo 'Build Number: ${env.BUILD_NUMBER}' >> deployment.log
                    echo "Deployment Started: \$(date)" >> deployment.log
                    cp deployment.log /tmp/jenkins-receipt-gemini-webui.log
                    sync
                """
            }
        }
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        
        stage('Deploy Gemini WebUI') {
            steps {
                sh 'docker-compose down || true'
                sh 'docker-compose up --build -d'
            }
        }
    }
    
    post {
        always {
            sh 'docker-compose ps'
            withCredentials([string(credentialsId: 'Adam-Jenkins-Token', variable: 'ADAM_TOKEN')]) {
                sh """
                    curl -sL -u "adamoutler@gmail.com:${ADAM_TOKEN}" "${env.BUILD_URL}consoleText" > /tmp/jenkins-receipt-gemini-webui.log
                    echo "Finished: ${currentBuild.currentResult} #${env.BUILD_NUMBER}" >> /tmp/jenkins-receipt-gemini-webui.log
                """
            }
        }
    }
}