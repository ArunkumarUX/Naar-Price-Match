FROM node:22-alpine

WORKDIR /app

# Playwright browsers (Chromium only)
RUN apk add --no-cache chromium nss freetype harfbuzz ca-certificates ttf-freefont \
  && apk add --no-cache --virtual .build-deps curl \
  && rm -rf /var/cache/apk/*

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

COPY package*.json ./
RUN npm install

COPY . .
RUN npx prisma generate

EXPOSE 8000

CMD ["npm", "start"]
