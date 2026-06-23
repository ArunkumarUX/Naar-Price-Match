FROM node:22-alpine

WORKDIR /app

# System Chromium for Playwright (no `playwright install --with-deps` needed)
RUN apk add --no-cache chromium nss freetype harfbuzz ca-certificates ttf-freefont

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV NODE_ENV=production

COPY package*.json ./
RUN npm install

COPY . .
RUN npx prisma generate && npm run build

EXPOSE 8000

CMD ["sh", "-c", "npx prisma migrate deploy && node dist/api/server.js"]
