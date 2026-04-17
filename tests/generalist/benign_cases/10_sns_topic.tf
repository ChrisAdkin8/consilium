resource "aws_sns_topic" "alerts" {
  name = "platform-alerts"
  tags = {
    owner = "platform-team"
  }
}
