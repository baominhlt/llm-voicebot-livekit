def GetNameSpace() {
    def namespace = ""
    if ("dev".equals(BRANCH_NAME)){
        namespace = "ai"
    } else {
        namespace = "unknown"
    }
    return namespace
}

def GetRepository() {
    def repository = "ai.llm-based-voicebot.llm-voicebot-livekit"
    return repository
}

pipeline {
    agent { label 'master' }
    environment {
        WEBHOOK_URL = credentials("vqc-telegram-webhook")
        TELEGRAM_USER_ID = credentials("vqc-telegram-user-id")
        ECR_REGISTRY = credentials("vqc-ecr-registry")
        DEPLOYMENT_NAME = "llm-voicebot-livekit"
        SERVICE_NAME = "llm-voicebot-livekit"
        SONARSERVER = "sonarserver"
        SONARSCANNER = "sonarscanner"
        ECR_TAG = """${sh(
            returnStdout: true,
            script: ' git describe --always '
        )}""".trim()
    }

    stages {
        // Prepare the workspace
        stage('Prepare the workspace for development') {
            steps {
                script {
                    if (env.BRANCH_NAME == 'prod') {
                        sh """
                            curl -s --max-time 10 \
                            -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=🛠 Pending (Click "Proceed" in Jenkins Server to continue)  %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
                            """
                        input message: 'Deploy to production (Click "Proceed" to continue)'         
                    } 
                    sh """
                        curl -s --max-time 10 \
                        -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=⏰ Running  %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
                    """
                }
            }
        }

        // Scan code
        stage('SonarQube Analysis') {
            when {
            	branch 'dev'
            }
            environment {
                scannerHome = tool "${SONARSCANNER}"
            }
            steps {
                withSonarQubeEnv("${SONARSERVER}") {
                    sh "${scannerHome}/bin/sonar-scanner"
                }
            }
        }

        // Build and Push
        stage('Build and Push image to registry') {
            steps {
                script {
                    ECR_REPOSITORY = GetRepository()
                    docker.withRegistry("https://${ECR_REGISTRY}", "ecr:ap-southeast-1:aws-credentials-563506675681") {
                        def dockerImage = docker.build("${ECR_REPOSITORY}:${BRANCH_NAME}-${ECR_TAG}") 
                        dockerImage.push()
                    }
                }
            }
        }

        // Deploy
        // stage('Deploy new commit') {
        //     steps {

        //     }
        // }
    }

    post {
        success {
            sh """
                curl -s --max-time 10 \
                -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=Deploy status: ✅ success %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
            """
        }

        failure {
            sh """
                curl -s --max-time 10 \
                -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=Deploy status: ❌ failure %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
            """
        }

        aborted {
            sh """
                curl -s --max-time 10 \
                -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=Deploy status: ❌ aborted %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
            """
        }

        unstable {
            sh """
                curl -s --max-time 10 \
                -d 'chat_id=${TELEGRAM_USER_ID}&disable_web_page_preview=1&text=Deploy status: ❌ unstable %0A%0AJob name: ${JOB_NAME}%0ABranch: ${BRANCH_NAME}%0AGit commit: ${GIT_COMMIT}' ${WEBHOOK_URL} > /dev/null
            """
        }

        always {
            deleteDir()
        }
    }
}