export const metadata = {
  title: "EdgeAlert TrendSpider M5 • XAU/USD Tiempo Real",
  description: "Motor Institucional XAU/USD con Modo Continuo Android, Wake Lock y Alertas de Voz",
  manifest: "/manifest.json",
  themeColor: "#f59e0b",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <head>
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="theme-color" content="#08090c" />
        <link rel="manifest" href="/manifest.json" />
      </head>
      <body style={{ fontFamily: "Arial, sans-serif", background: "#08090c", color: "white", margin: 0, WebkitTapHighlightColor: "transparent" }}>
        {children}
      </body>
    </html>
  );
}