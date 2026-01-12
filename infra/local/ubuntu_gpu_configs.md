pip install "ray[serve,llm]

ray start --address=192.168.214.21:6380 --node-ip-address=192.168.214.22

vllm chat --url http://192.168.214.21:8000/v1

vllm serve BAAI/bge-m3 \
  --port 8080 \
  --task embed \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.15