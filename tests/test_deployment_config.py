"""
DEPLOYMENT CONFIGURATION TESTS — Phase 6/7.

Static validation only — `docker build`/`docker compose up` cannot
execute in this environment (no network access to pull base images;
confirmed across three independent channels — pip, npm, and a real
`apt-get install postgresql`, all returning 403 Forbidden — see
docs/runtime-verification.md and the Phase 6/7 reports). These tests
prove the configuration files are well-formed and internally
consistent, not that Docker can actually run them. STATICALLY
VERIFIED, never claimed as RUNTIME VERIFIED — see DEPLOYMENT.md's
readiness matrix.

Deliberately stdlib-only, matching every other test in this suite:
PyYAML happens to be pre-installed in the sandbox that produced this
codebase, but it is not declared in requirements.txt and is not a
stdlib module, so depending on it here would silently make this test
file fail in any other environment. Plain string/line checks are
enough for what these tests actually need to verify.
"""
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DockerComposeTestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, "docker-compose.yml")) as f:
            self.content = f.read()
        self.lines = self.content.splitlines()

    def test_declares_exactly_the_three_expected_services(self):
        # Top-level service names are the only lines indented exactly
        # two spaces directly under "services:".
        in_services = False
        found = []
        for line in self.lines:
            if line.strip() == "services:":
                in_services = True
                continue
            if in_services:
                if line and not line.startswith(" "):
                    break  # left the services: block
                if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
                    found.append(line.strip().rstrip(":"))
        self.assertEqual(set(found), {"db", "api", "frontend"})

    def test_db_service_uses_a_real_postgres_image_with_a_health_check(self):
        self.assertIn("image: postgres:16", self.content)
        self.assertIn("healthcheck:", self.content)
        self.assertIn("pg_isready", self.content)

    def test_db_service_is_not_publicly_exposed(self):
        """Phase 7 finding, fixed: the db service previously published
        5432:5432 to the host, letting anyone who can reach the host
        connect directly to PostgreSQL, bypassing every application-
        layer auth/authz/audit control. The api service reaches it via
        Docker's internal DNS (db:5432) regardless of any host port
        mapping — none is needed for the app to function."""
        db_block_start = self.content.index("  db:")
        api_block_start = self.content.index("  api:")
        db_block = self.content[db_block_start:api_block_start]
        # Only real YAML lines matter here — the explanatory comment
        # documenting *why* this was removed necessarily quotes the old
        # mapping as text, which a bare substring check would wrongly
        # flag as if the mapping were still active.
        active_lines = [line for line in db_block.splitlines() if line.strip() and not line.strip().startswith("#")]
        active_content = "\n".join(active_lines)
        self.assertNotIn("5432:5432", active_content)
        self.assertNotIn("ports:", active_content)

    def test_api_service_waits_for_a_healthy_database_before_starting(self):
        self.assertIn("condition: service_healthy", self.content)

    def test_api_service_database_url_matches_the_db_service_credentials(self):
        self.assertIn("POSTGRES_USER: asavexa", self.content)
        self.assertIn("POSTGRES_PASSWORD: asavexa", self.content)
        self.assertIn("POSTGRES_DB: asavexa", self.content)
        self.assertIn("postgresql+psycopg://asavexa:asavexa@db:5432/asavexa", self.content)

    def test_frontend_builds_from_its_own_dockerfile_rather_than_a_raw_bind_mount(self):
        """Phase 7 finding, fixed: the frontend service previously
        bind-mounted the entire frontend/ directory as nginx's webroot,
        which made nginx.conf itself (and tests/) publicly fetchable —
        curl http://localhost:8080/nginx.conf would have returned the
        internal proxy config verbatim. Building from frontend/Dockerfile
        (which COPYs only index.html and src/) fixes this structurally:
        there is nothing else in the image to accidentally serve."""
        frontend_block_start = self.content.index("  frontend:")
        frontend_block = self.content[frontend_block_start:]
        self.assertIn("build:", frontend_block)
        self.assertIn("./frontend", frontend_block)
        self.assertNotIn("usr/share/nginx/html", frontend_block, "no raw bind mount of the whole directory")

    def test_every_service_has_a_restart_policy(self):
        self.assertEqual(self.content.count("restart: unless-stopped"), 3)

    def test_ports_do_not_collide_across_services(self):
        host_ports = []
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith('- "') and ":" in stripped:
                host_port = stripped.split('"')[1].split(":")[0]
                host_ports.append(host_port)
        self.assertEqual(len(host_ports), len(set(host_ports)), f"duplicate host port mapping in {host_ports}")


class DockerfileTestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, "Dockerfile")) as f:
            self.content = f.read()

    def test_installs_from_requirements_txt_not_ad_hoc_pip_installs(self):
        self.assertIn("requirements.txt", self.content)
        self.assertIn("pip install", self.content)

    def test_runs_migrations_before_starting_the_server(self):
        cmd_line = next(line for line in self.content.splitlines() if line.startswith("CMD"))
        self.assertIn("alembic upgrade head", cmd_line)
        self.assertIn("uvicorn", cmd_line)
        self.assertLess(cmd_line.index("alembic"), cmd_line.index("uvicorn"),
                         "migrations must run before the server starts, not after")

    def test_sets_pythonpath_to_src_matching_the_rest_of_the_project(self):
        self.assertIn("PYTHONPATH=/app/src", self.content)

    def test_copies_migrations_and_schema_into_the_image(self):
        self.assertIn("migrations/", self.content)
        self.assertIn("schema.sql", self.content)
        self.assertIn("alembic.ini", self.content)

    def test_runs_as_a_non_root_user(self):
        """Phase 7 finding, fixed: the image previously had no USER
        directive at all, running as root for its entire lifetime."""
        self.assertIn("useradd", self.content)
        self.assertIn("USER asavexa", self.content)
        # The USER switch must come after the app files are chowned,
        # and before the final CMD — not merely present anywhere.
        self.assertLess(self.content.index("USER asavexa"), self.content.rindex("CMD ["))

    def test_declares_a_container_health_check(self):
        """Phase 7 finding, fixed: only the compose file's *database*
        service had a health check; the API container itself had none."""
        self.assertIn("HEALTHCHECK", self.content)
        self.assertIn("/health", self.content)

    def test_health_check_targets_liveness_not_readiness(self):
        """Docker restarts a container it considers unhealthy — that
        must never happen merely because the database is briefly
        unreachable, which is what /ready (checked separately) is for."""
        # Find the actual instruction line (starts with "HEALTHCHECK "),
        # not an earlier mention of the word inside an explanatory
        # comment — a bare substring search would find the comment first.
        instruction_line = next(
            line for line in self.content.splitlines() if line.startswith("HEALTHCHECK ")
        )
        # The CMD clause of a HEALTHCHECK instruction is on the next
        # line(s) after a line-continuation backslash.
        idx = self.content.index(instruction_line)
        healthcheck_block = self.content[idx:idx + 400]
        self.assertIn("/health", healthcheck_block)
        self.assertNotIn("/ready", healthcheck_block)


class FrontendDockerfileTestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, "frontend", "Dockerfile")) as f:
            self.content = f.read()

    def test_copies_only_public_files_never_nginx_conf_into_the_html_root(self):
        html_copies = [line for line in self.content.splitlines() if "usr/share/nginx/html" in line]
        self.assertTrue(html_copies)
        combined = "\n".join(html_copies)
        self.assertIn("index.html", combined)
        self.assertIn("src/", combined)
        self.assertNotIn("nginx.conf", combined, "nginx.conf must never be copied into the served html root")
        self.assertNotIn("tests", combined, "tests/ must never be copied into the served html root")

    def test_nginx_conf_is_installed_as_the_actual_server_config_not_public_content(self):
        self.assertIn("/etc/nginx/conf.d/default.conf", self.content)


class NginxConfigTestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, "frontend", "nginx.conf")) as f:
            self.content = f.read()

    def test_reverse_proxies_api_with_the_correct_upstream(self):
        self.assertIn("proxy_pass http://api:8000", self.content)
        self.assertIn("location /api/", self.content)

    def test_declares_baseline_security_headers(self):
        """Phase 7 finding, fixed: no security headers existed at all."""
        for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
            self.assertIn(header, self.content)

    def test_denies_dotfiles_and_the_nginx_config_itself_as_defense_in_depth(self):
        self.assertIn("location ~ /\\.", self.content)
        self.assertIn("/nginx.conf", self.content)
        self.assertIn("deny all", self.content)

    def test_declares_a_bounded_request_body_size(self):
        self.assertIn("client_max_body_size", self.content)

    def test_declares_proxy_timeouts_not_left_to_defaults(self):
        self.assertIn("proxy_connect_timeout", self.content)
        self.assertIn("proxy_read_timeout", self.content)

    def test_forwards_client_ip_and_protocol_headers_to_the_api(self):
        self.assertIn("X-Real-IP", self.content)
        self.assertIn("X-Forwarded-For", self.content)
        self.assertIn("X-Forwarded-Proto", self.content)


class EnvExampleTestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, ".env.example")) as f:
            self.content = f.read()

    def test_declares_database_url_and_cors_allowed_origins(self):
        self.assertIn("DATABASE_URL=", self.content)
        self.assertIn("CORS_ALLOWED_ORIGINS=", self.content)

    def test_cors_example_origins_match_what_the_frontend_docs_describe(self):
        self.assertIn("localhost:5173", self.content)

    def test_no_value_looks_like_a_real_leaked_credential(self):
        # The only "password"-shaped value here must be the well-known
        # local-dev placeholder, not something with real-looking entropy.
        self.assertIn("asavexa:asavexa@localhost", self.content)


if __name__ == "__main__":
    unittest.main()
