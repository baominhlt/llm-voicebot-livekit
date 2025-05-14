#!/bin/bash

export VERSION=1.0
export PORT=10000

docker build . -t llm-voicebot-livekit:$VERSION
docker run --rm -it \
-p $PORT:80 \
--env-file=.env \
--name=llm-voicebot-livekit \
llm-voicebot-livekit:$VERSION
