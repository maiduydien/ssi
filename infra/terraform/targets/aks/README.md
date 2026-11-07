# AKS alternative (optional learning target)

AKS is intentionally not the default hosting path for this small Dash app. It adds Kubernetes operations, cluster networking, node capacity, upgrade and security responsibilities, and potentially significant cost.

The Terraform here creates a basic AKS cluster and grants its kubelet identity `AcrPull`. It does not automatically deploy the application. After the cluster is created:

1. Configure `kubectl` using Azure CLI.
2. Replace the image placeholder in `infra/kubernetes/deployment.yaml` with an immutable ACR image.
3. Apply the Deployment and Service.
4. Add ingress, TLS, network policy, autoscaling, secret integration, monitoring, and backup strategy before any production use.

Do not run this target concurrently with ACA/App Service unless intentionally testing multiple hosting models.
