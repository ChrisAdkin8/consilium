resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/app/web"
  retention_in_days = 30
  tags = {
    owner = "platform-team"
  }
}
