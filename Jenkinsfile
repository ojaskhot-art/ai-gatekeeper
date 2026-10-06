pipeline {
    agent any
    environment {
        GEMINI_API_KEY   = credentials('ai-api-key')
        GEMINI_MODEL     = 'gemini-3.1-flash-lite'
        PYTHONIOENCODING = 'utf-8'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Build & Test') {
            steps {
                bat 'py -m pip install -r requirements.txt'
                bat 'py -m pytest -q'
            }
        }
        stage('AI Review') {
            steps { bat 'py ai_review.py' }
        }
    }
    post {
        always {
            publishHTML(target: [
                reportDir: '.', reportFiles: 'review.html',
                reportName: 'AI Review Report',
                keepAll: true, alwaysLinkToLastBuild: true, allowMissing: true
            ])
            archiveArtifacts artifacts: 'RELEASE_NOTES.md, review.html', allowEmptyArchive: true
        }
    }
}
