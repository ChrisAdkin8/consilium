resource "aws_subnet" "private_c" {
  vpc_id            = "vpc-1234"
  cidr_block        = "10.0.3.0/24"
  availability_zone = "us-east-1c"
  tags = {
    owner = "network-team"
    tier  = "private"
  }
}
