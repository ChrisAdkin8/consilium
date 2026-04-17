resource "aws_security_group" "web" {
  name        = "web"
  description = "Allow HTTPS from VPC"
  vpc_id      = "vpc-1234"

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  tags = {
    owner = "platform-team"
  }
}
