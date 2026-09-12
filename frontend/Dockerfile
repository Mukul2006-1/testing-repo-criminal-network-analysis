FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Browser-reachable backend URL, baked at container start (vite dev reads
# process env on startup). Override per environment; never a secret here.
ENV VITE_API_BASE_URL=http://localhost:8000

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
