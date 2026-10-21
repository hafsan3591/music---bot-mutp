# Node.js 18 (slim) ইমেজ থেকে শুধু node বাইনারি ও npm মডিউল নেওয়ার জন্য
FROM node:18-bullseye-slim AS node
FROM python:3.10-slim

# Node বাইনারি ও گلوبাল মডিউল Python ইমেজে কপি করা হচ্ছে
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

# প্রয়োজনীয় সিস্টেম প্যাকেজ ইনস্টল:
# ffmpeg  -> অডিও/ভিডিও প্রসেসিং
# git     -> কিছু Python প্যাকেজ git থেকে ইনস্টল হতে পারে
# curl    -> ডাউনলোড/হেলথচেক
# fonts-dejavu-core -> থাম্বনেইলে টেক্সট রেন্ডারিং
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/

# pip আপগ্রেড করে requirements.txt থেকে ডিপেন্ডেন্সি ইনস্টল
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt

# কন্টেইনার চালু হলে app.py চালানো হবে
CMD ["python3", "app.py"]