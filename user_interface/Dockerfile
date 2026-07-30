# user_interface/Dockerfile
# Dev-mode image: runs `next dev` with the source bind-mounted for hot
# reload (see the `sheria-ui` service in the root docker-compose.yml) rather
# than a production `next build`.
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
