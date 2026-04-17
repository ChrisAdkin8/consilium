job "consilium-kb-mcp" {
  datacenters = ["dc1"]
  type        = "service"

  group "kb-mcp" {
    count = 1

    network {
      port "http" {
        static = 8000
      }
    }

    service {
      name = "consilium-kb-mcp"
      port = "http"
      tags = ["consilium", "mcp", "kb"]

      check {
        name     = "tcp-alive"
        type     = "tcp"
        interval = "10s"
        timeout  = "3s"
      }
    }

    task "server" {
      driver = "docker"

      config {
        image   = "consilium/kb-mcp:latest"
        command = "python"
        args    = ["-m", "kb_extensions.mcp_server"]
        ports   = ["http"]
      }

      env {
        NEO4J_URI        = "bolt://${attr.unique.network.ip-address}:7687"
        NEO4J_USER       = "neo4j"
        CONSUL_HTTP_ADDR = "http://${attr.unique.network.ip-address}:8500"
        KB_MCP_PORT      = "8000"
        KB_MCP_HOST      = "0.0.0.0"
      }

      template {
        data = <<EOF
{{ with secret "consilium/data/neo4j" }}
NEO4J_PASS={{ .Data.data.password }}
{{ end }}
EOF

        destination = "local/neo4j.env"
        env         = true
      }

      resources {
        cpu    = 256
        memory = 256
      }

      logs {
        max_files     = 5
        max_file_size = 10
      }
    }
  }
}
