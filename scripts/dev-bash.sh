#!/usr/bin/env bash

docker run -it --privileged -v $(pwd):/workspace \
  -p 5000:5000 -p 9000:9000 -p 9001:9001 -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  imageml-dev bash
