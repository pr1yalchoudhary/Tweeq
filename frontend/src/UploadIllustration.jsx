/** Original vector artwork: two illuminated voice silhouettes and a floating sound ribbon. */
export default function UploadIllustration() {
  return <svg className="voice-illustration" viewBox="0 0 280 240" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="voice-neutral" x1="50" y1="30" x2="165" y2="210" gradientUnits="userSpaceOnUse"><stop stopColor="#f5f5f3"/><stop offset="1" stopColor="#dededb"/></linearGradient>
      <linearGradient id="voice-warm" x1="140" y1="35" x2="240" y2="215" gradientUnits="userSpaceOnUse"><stop stopColor="#fff3df"/><stop offset=".55" stopColor="#ffe0bd"/><stop offset="1" stopColor="#ffc186"/></linearGradient>
      <radialGradient id="voice-silver"><stop stopColor="#e4e5e3"/><stop offset=".65" stopColor="#bcbfbc"/><stop offset="1" stopColor="#d9dbd8"/></radialGradient>
      <radialGradient id="voice-orange" cx=".35" cy=".25" r=".85"><stop stopColor="#ffe4a7"/><stop offset=".45" stopColor="#ffb44f"/><stop offset=".8" stopColor="#ef962f"/><stop offset="1" stopColor="#ffd398"/></radialGradient>
      <linearGradient id="voice-ribbon"><stop stopColor="white"/><stop offset="1" stopColor="#fff9f0"/></linearGradient>
      <filter id="voice-shadow" x="-30%" y="-40%" width="160%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>
      <path id="voice-person" d="M18 178c1-20 17-26 37-34 8-3 13-8 13-18v-7c-10-6-15-16-16-29-5 0-7-5-7-11 0-5 2-8 5-8-3-31 9-49 33-49s39 18 35 49c4 0 6 3 6 8 0 6-3 11-7 11-1 13-7 24-16 29v7c0 10 5 15 13 18 20 8 36 14 38 34v12H18z"/>
    </defs>
    <ellipse cx="153" cy="220" rx="106" ry="7" fill="#afa397" opacity=".13" filter="url(#voice-shadow)"/>
    <path d="M31 192V96a67 67 0 0 1 134 0v96z" fill="url(#voice-neutral)"/>
    <use href="#voice-person" transform="translate(16 32) scale(.87)" fill="url(#voice-silver)" opacity=".88"/>
    <path d="M133 215V103a72 72 0 0 1 144 0v112a13 13 0 0 1-13 13H146a13 13 0 0 1-13-13z" fill="url(#voice-warm)" stroke="white" strokeWidth="2" transform="translate(-7 -1)"/>
    <use href="#voice-person" transform="translate(119 37) scale(.94)" fill="url(#voice-orange)"/>
    <rect x="60" y="190" width="193" height="34" rx="17" fill="#b09b82" opacity=".14" filter="url(#voice-shadow)"/>
    <rect x="58" y="183" width="193" height="35" rx="17.5" fill="url(#voice-ribbon)" stroke="white" strokeWidth="2"/>
    {[7,13,21,12,25,16,9].map((h,i)=><rect key={i} x={75+i*8} y={200-h/2} width="3" height={h} rx="1.5" fill="#c9ccca"/>)}
    <circle cx="155" cy="200" r="14" fill="#20201e"/>
    <path d="M148 197h13l-4-4m4 10h-13l4 4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    {[9,17,24,14,21,12,7].map((h,i)=><rect key={i} x={178+i*8} y={200-h/2} width="3" height={h} rx="1.5" fill="#f6ae73"/>)}
  </svg>
}
