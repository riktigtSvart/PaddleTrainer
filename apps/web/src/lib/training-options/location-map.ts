export const MAP_WIDTH = 800, MAP_HEIGHT = 320;
export function mapPixel(latitude: number, longitude: number, zoom: number): [number,number] {
  const size=256*2**zoom,lat=Math.max(-85.05112878,Math.min(85.05112878,latitude))*Math.PI/180;
  return [(longitude+180)/360*size,(1-Math.asinh(Math.tan(lat))/Math.PI)/2*size];
}
export function mapCoordinate(x: number,y: number,zoom: number): [number,number] {
  const size=256*2**zoom;
  return [Math.atan(Math.sinh(Math.PI*(1-2*y/size)))*180/Math.PI,x/size*360-180];
}
export function decimalDegree(v: number) { return Number(v.toFixed(7)).toString(); }
