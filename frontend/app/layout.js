export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#08090c"
};

export const metadata = {
  title: "EdgeAlert TrendSpider M5 • XAU/USD Tiempo Real",
  description: "Motor Institucional XAU/USD con Modo Continuo Android, Wake Lock y Alertas de Voz",
  manifest: "/manifest.json",
  icons: {
    icon: "/icon-192.png",
    apple: "/icon-192.png"
  }
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <head>
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="application-name" content="EdgeAlert" />
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" href="/icon-192.png" />
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body style={{ fontFamily: "Arial, sans-serif", background: "#08090c", color: "white", margin: 0, WebkitTapHighlightColor: "transparent" }}>
        {children}
      </body>
    </html>
  );
}