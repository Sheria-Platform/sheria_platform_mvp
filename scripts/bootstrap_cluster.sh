# scripts/bootstrap_cluster.sh
#!/bin/bash

# 1. Install KubeRay Operator (Manages Ray Clusters)
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0

# 2. Install External Secrets (Syncs AWS Secrets Manager -> K8s)
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets

# 3. Install Nginx Ingress (Load Balancer Controller)
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx