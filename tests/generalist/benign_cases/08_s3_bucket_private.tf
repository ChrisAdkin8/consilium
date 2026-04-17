resource "aws_s3_bucket" "artifacts" {
  bucket = "acme-ci-artifacts-2026"
  tags = {
    owner = "platform-team"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
