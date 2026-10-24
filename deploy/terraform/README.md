# Terraform provider notes

Each provider has a separate Terraform root module because each VPS provider
uses a different API. Apply one provider module, then run the shared Ansible
playbook. The existing directory only produces inventory data and does not
provision or modify a server.

## Provider coverage

| Provider | Creates a VPS | Notes |
| --- | --- | --- |
| Hetzner Cloud | Yes | AlmaLinux 10 default; server size, image, and location are configurable. |
| IONOS Cloud | Yes | Creates a VDC, public LAN/IP, and VM; set an image alias available to the account. |
| Contabo | Yes | Requires account-specific product, image, and uploaded SSH-key IDs. |
| netcup | No | Use the existing-server path; the available SCP API does not create/delete VPS contracts. |
| dogado | No | Use the existing-server path; its public Cloud Server API does not order VPS instances. |
| STRATO, centron, webgo, Alfahosting, IP-Projects | Existing server | No validated create-VPS Terraform adapter is included. |

The list is a practical shortlist of providers based in Germany that offer
VPS products, not a measured market-share ranking. Provider APIs and community
Terraform providers can change; review each plan and provider documentation
before applying.

## Existing VPS

terraform/existing does not create or change a server. It formats an inventory
entry from a hostname/IP and SSH user:

    cd deploy/terraform/existing
    cp terraform.tfvars.example terraform.tfvars
    terraform init
    terraform apply
    terraform output -raw ansible_inventory_ini > ../../ansible/inventory.ini

You can also skip this helper and edit the Ansible inventory directly.

## Credentials and state

Supply credentials through environment variables rather than committed
terraform.tfvars files:

- Hetzner Cloud: HCLOUD_TOKEN
- IONOS Cloud: IONOS_TOKEN
- Contabo: CNTB_OAUTH2_CLIENT_ID, CNTB_OAUTH2_CLIENT_SECRET,
  CNTB_OAUTH2_USER, CNTB_OAUTH2_PASS

Terraform state can contain infrastructure metadata. Do not commit it or
terraform.tfvars files. No remote backend is selected because the appropriate
state service depends on the team.

## Module details

Hetzner Cloud defaults to cx23 (2 vCPU, 4 GB RAM, 40 GB disk). AlmaLinux 10
is the default image; set image to debian-13 for Debian. Its cloud firewall
allows SSH from ssh_allowed_cidrs and TCP 80/443 from the Internet.

IONOS defaults to 2 vCPU, 4 GB RAM, and 40 GB SSD. image_name must match an
image/alias in the IONOS account. ssh_allowed_ipv4 accepts one IPv4 source
address without a CIDR suffix; the Ansible host firewall can further limit
SSH by CIDR.

Contabo product and image IDs depend on the account and selected plan. Set
product_id, image_id, and ssh_key_secret_ids for that account.
