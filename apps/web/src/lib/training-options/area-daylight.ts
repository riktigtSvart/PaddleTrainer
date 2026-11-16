import { solarPosition } from "./solar";
import type { DaylightRule, GeographicArea } from "./daylight-rules";
export const AREA_SOLAR_METHOD = "area-common-light-v0.1";
const rad = (v: number) => v * Math.PI / 180;
export function minimumAreaAltitude(t: number, area: GeographicArea) {
  const [declination, equation] = solarPosition(t), angle = (((t % 86400) + 86400) % 86400 / 60 + equation) / 4 - 180;
  const a = rad(angle + Number(area.west)), b = rad(angle + Number(area.east));
  let minimumCos = Math.min(Math.cos(a), Math.cos(b));
  if (Math.ceil((a-Math.PI)/(2*Math.PI)) <= Math.floor((b-Math.PI)/(2*Math.PI))) minimumCos = -1;
  const x = Math.sin(declination), y = Math.cos(declination)*minimumCos;
  const low = rad(Number(area.south)), high = rad(Number(area.north)), latitudes = [low,high], stationary = Math.atan2(x,y);
  for (let k=-2;k<=2;k++) { const v=stationary+k*Math.PI;if(low<=v&&v<=high)latitudes.push(v); }
  return Math.asin(Math.max(-1,Math.min(1,...latitudes.map(v=>x*Math.sin(v)+y*Math.cos(v)))))*180/Math.PI;
}
const cache = new Map<string,number[]>();
function altitudes(day: number, area: GeographicArea) {
  const key = [day,area.south,area.north,area.west,area.east].join("|");
  let values = cache.get(key);
  if (!values) { values=Array.from({length:1440},(_,m)=>minimumAreaAltitude(day*86400+m*60+30,area));if(cache.size>=512)cache.delete(cache.keys().next().value!);cache.set(key,values); }
  return values;
}
export function areaLightIntervals(first: number,last: number,area: GeographicArea,rule: DaylightRule): [number,number][] {
  const threshold = rule.mode === "daylight" ? -.833 : -6, windows: [number,number][]=[];
  let opened: number|null=null;
  for(let day=Math.floor(first/86400)-2;day<Math.floor(last/86400)+3;day++)
    altitudes(day,area).forEach((alt,m)=>{const t=day*86400+m*60,above=alt>=threshold+.2;
      if(above&&opened===null)opened=t;else if(!above&&opened!==null){windows.push([opened,t]);opened=null;}});
  if(opened!==null)windows.push([opened,(Math.floor(last/86400)+3)*86400]);
  return windows.map(([a,b])=>[Math.max(first,a+rule.start_buffer_minutes*60),Math.min(last,b-rule.end_buffer_minutes*60)] as [number,number]).filter(([a,b])=>a<b);
}
