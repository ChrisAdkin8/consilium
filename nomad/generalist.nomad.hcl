job "consilium-generalist" {
  datacenters = ["dc1"]
  type        = "service"

  group "generalist" {
    count = 1

    network {
      port "http" {
        static = 8004
      }
    }

    service {
      name = "consilium-generalist"
      port = "http"
      tags = ["consilium", "agent", "voter", "soft-concern"]

      check {
        name     = "tcp-alive"
        type     = "tcp"
        interval = "10s"
        timeout  = "3s"
      }
    }

    task "agent" {
      driver = "docker"

      config {
        image   = "consilium/generalist:latest"
        command = "python"
        args    = ["-m", "agents.generalist.main"]
        ports   = ["http"]
      }

      env {
        VAULT_ADDR       = "http://${attr.unique.network.ip-address}:8200"
        CONSUL_HTTP_ADDR = "http://${attr.unique.network.ip-address}:8500"
        MCP_URL          = "http://${attr.unique.network.ip-address}:8000/mcp"
        AGENT_NAME       = "generalist"
        AGENT_MODEL      = "claude-sonnet-4-6"
        VOTER_CLASS      = "soft_concern"
        AGENT_PORT       = "8004"
        AGENT_HOST       = "0.0.0.0"
      }

      template {
        data = <<EOF
{{ with secret "auth/approle/role/consilium-generalist/role-id" }}
VAULT_APPROLE_ROLE_ID={{ .Data.role_id }}
{{ end }}
{{ with secret "auth/approle/role/consilium-generalist/secret-id" }}
VAULT_APPROLE_SECRET_ID={{ .Data.secret_id }}
{{ end }}
EOF

        destination = "secrets/approle.env"
        env         = true
      }

      resources {
        cpu    = 512
        memory = 512
      }

      logs {
        max_files     = 5
        max_file_size = 10
      }
    }
  }
}
