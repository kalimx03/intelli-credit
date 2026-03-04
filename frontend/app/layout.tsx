import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Intelli-Credit | AI Credit Decisioning',
  description: 'AI-powered corporate credit decisioning engine for Indian banking',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700;800&display=swap" rel="stylesheet" />
        <style>{`*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; } body { font-family: 'IBM Plex Sans', sans-serif; } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </head>
      <body>{children}</body>
    </html>
  );
}
