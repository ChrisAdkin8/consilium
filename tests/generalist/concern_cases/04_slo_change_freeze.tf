resource "aws_db_instance" "payments" {
  identifier        = "payments-primary"
  instance_class    = "db.r6i.2xlarge"
  engine            = "postgres"
  storage_encrypted = true
  tags = {
    owner = "payments-team"
  }
}
