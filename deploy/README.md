# Fire Elite Deployment

This directory contains Terraform examples and one Ansible playbook for
deploying Fire Elite. The playbook supports AlmaLinux and Debian and works with
either a newly provisioned VPS or an existing server.

## Supported setup paths

1. Create a VPS with Terraform in one of the provider directories, then run
   Ansible against its address.
2. Use an existing Linux VPS and run the same Ansible playbook directly.
   Terraform's existing directory can format an inventory entry, but does not
   change that server.

The practical provider shortlist is Hetzner, IONOS, STRATO, Contabo, netcup,
dogado, centron, webgo, Alfahosting, and IP-Projects. This is a working
shortlist of German-based providers with VPS offers, not a measured ranking.
The initial create-VPS modules cover Hetzner Cloud, IONOS Cloud, and Contabo.
For the other providers, use the existing-server path unless a supported
Terraform create API is added.

## Server sizing

Plan for at least 2 vCPU, 4 GB RAM, and 40 GB persistent disk for a small
installation. This is a practical starting estimate for the app and its
PostgreSQL container, not an official hard minimum published by the app.
Increase storage to match the number of users and retained backups.

## Deploy to an existing VPS

1. Install Terraform and Ansible on the control machine.
2. Edit ansible/group_vars/all.yml. Set the real domain, proxy mode, SSH
   source CIDRs, and any SMTP settings.
3. Copy the secrets example, replace the placeholders, and encrypt it:

       cd deploy/ansible
       cp secrets.yml.example secrets.yml
       openssl rand -hex 24
       openssl rand -hex 32
       ansible-vault encrypt secrets.yml

   Use the first generated value for the PostgreSQL password and the second
   for the session key. The database password must remain URL-safe. Choose a
   unique administrator password with at least 14 characters.
4. Copy inventory.ini.example to inventory.ini and set the server address and
   SSH account. Keep the matching private key on the control machine.
5. Install the Ansible collection and deploy:

       ansible-galaxy collection install -r requirements.yml
       ansible-playbook -i inventory.ini playbook.yml --ask-vault-pass

The secrets file is written to root-only environment files on the server.
Ansible Vault protects the copy kept in the repository workspace.

## Domain, proxy, and firewall

The default proxy mode runs Caddy in Docker and obtains HTTPS certificates
automatically. Point the domain's A/AAAA records to the VPS and allow inbound
TCP 80 and 443.

For an existing reverse proxy on the same server, set fire_elite_proxy_mode to
external. The app then binds to 127.0.0.1:8086 by default. Configure that proxy
to forward HTTPS requests to this local port. Do not expose the app port
directly to the Internet.

The host firewall can be managed by Ansible. Set
fire_elite_ssh_allowed_cidrs to the administrator's public IP/CIDR before
deployment so the playbook does not lock out SSH. Provider firewalls should
allow TCP 22 from those same ranges and TCP 80/443 from the Internet when
Caddy or the host proxy uses those ports. On a VPS that already serves other
applications, review the existing firewall policy before enabling
fire_elite_manage_host_firewall.

AlmaLinux is the preferred OS default; Debian is also supported. Docker
directly lists Debian and RHEL/CentOS. AlmaLinux uses Docker's CentOS-compatible
RPM repository.

## Create a VPS with Terraform

Choose one directory: terraform/hetzner, terraform/ionos, or terraform/contabo.
Copy that directory's terraform.tfvars.example to terraform.tfvars, fill in
provider-specific values, and supply credentials through environment
variables. See terraform/README.md for the credential names and limitations.

From the selected provider directory:

    terraform init
    terraform plan
    terraform apply
    terraform output -raw ansible_inventory_ini > ../../ansible/inventory.ini

Review the plan before applying it. Terraform state can contain infrastructure
metadata; keep it out of Git and store it securely.

## Data, backups, and updates

PostgreSQL data is stored under fire_elite_data_dir/postgres. Fire Elite's
compressed database backups are stored under fire_elite_data_dir/backups.
Both locations persist across container replacement.

Fire Elite already schedules daily database backups. The default time is
03:00 Europe/Berlin and the default retention is 14 backups. Change the time
and retention in the app's Settings page. These files remain on the VPS, so
copy them to separate storage for off-site disaster recovery.

The app image is pinned to release 1.9 by default. Change
fire_elite_image_tag to select another release, then rerun the playbook to
pull and deploy it. The initial administrator account is created only when
the database is empty; changing its Ansible password later does not reset an
existing account.

SMTP values are supplied through Ansible and can be changed in
ansible/group_vars/all.yml. ADMIN_EMAIL is used to initialize the report
recipient on first startup; later changes belong in the app's Settings page.

## Security notes

- Do not commit ansible/secrets.yml, inventory.ini, Terraform state,
  terraform.tfvars, plans, or private SSH keys.
- The PostgreSQL password is URL-safe because it is included in DATABASE_URL.
- The app and database are deployed as one Docker Compose project on one VPS.
- The app image is public in GitHub Container Registry; no registry login is
  required for a normal pull.
