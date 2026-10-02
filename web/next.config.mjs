/** @type {import('next').NextConfig} */
const nextConfig = {
  // A self-contained server bundle for the production Docker image.
  output: "standalone",
};

export default nextConfig;
