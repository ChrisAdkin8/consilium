resource "aws_instance" "web" {
  instance_type = "t3.small"
  tags = {
    owner = "platform-team"
  }
}
