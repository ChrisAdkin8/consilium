resource "aws_route_table" "public" {
  vpc_id = "vpc-1234"
  tags = {
    owner = "network-team"
  }
}
