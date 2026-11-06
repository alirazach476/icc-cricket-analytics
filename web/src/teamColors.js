// Kit-style accent colours for the scoreboard (decoration only; flags carry the identity).
const C = {
  India: '#1e6bd6', Australia: '#f2b600', England: '#c8102e', Pakistan: '#0b6b3a', 'South Africa': '#1a9b5a',
  'New Zealand': '#8b95a7', 'Sri Lanka': '#1d4e9e', Bangladesh: '#0e7c4a', Afghanistan: '#2b6cb0', 'West Indies': '#8a1f45',
  Zimbabwe: '#d62828', Ireland: '#1aa34a', Scotland: '#2a5db0', Netherlands: '#f97316', Namibia: '#2a5db0', Nepal: '#c8102e',
  Oman: '#c8102e', 'United Arab Emirates': '#0a8f4e', 'United States of America': '#2d4fa3', Canada: '#d80621', Kenya: '#b91c1c',
  Bermuda: '#d62828', 'Papua New Guinea': '#c8102e', 'Hong Kong': '#de2910', Italy: '#1b5bd8', Uganda: '#e6c200',
}
export const teamColor = (name, fallback = '#4c8dff') => C[name] || fallback
