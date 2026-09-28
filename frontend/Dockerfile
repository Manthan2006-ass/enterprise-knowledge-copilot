FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required inside Docker - Vite's default (localhost only)
# would make the dev server unreachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]