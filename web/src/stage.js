// Knockout stage labels: QF, SF and F are written on fixtures, results and scoreboards
const KO = {
  Quarterfinal: ['QF', 'Quarter-final'],
  Semifinal: ['SF', 'Semi-final'],
  Final: ['F', 'Final'],
}
export function stageInfo(stage) {
  const k = KO[stage]
  return k ? { ko: true, short: k[0], long: k[1] } : { ko: false, short: null, long: stage || '' }
}
