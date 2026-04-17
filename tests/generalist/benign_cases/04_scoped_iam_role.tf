resource "aws_iam_role" "ecs_task" {
  name = "ecs-task-web"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
  tags = {
    owner = "platform-team"
  }
}
