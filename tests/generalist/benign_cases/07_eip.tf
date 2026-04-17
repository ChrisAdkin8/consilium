resource "aws_eip" "nat" {
  domain = "vpc"
  tags = {
    owner = "network-team"
  }
}
