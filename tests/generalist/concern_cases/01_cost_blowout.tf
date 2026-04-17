resource "aws_instance" "batch" {
  instance_type = "m5.24xlarge"
  count         = 3
  tags = {
    owner = "data-team"
  }
}
