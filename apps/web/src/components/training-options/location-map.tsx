"use client";
import { useState } from "react";
import { MAP_WIDTH as W, MAP_HEIGHT as H, mapPixel, mapCoordinate, decimalDegree } from "@/lib/training-options/location-map";
import type { Coordinates, GeographicArea } from "@/lib/training-options/daylight-rules";
import { secondaryClass } from "@/components/planning-goals/fields";

export default function LocationMap({point,area,zone,mode,onPoint,onArea}: {point?:Coordinates;area?:GeographicArea;zone:string;mode:"point"|"area";onPoint:(p:Coordinates)=>void;onArea:(a:GeographicArea)=>void}) {
  const [zoom,setZoom]=useState(7),[centre,setCentre]=useState<[number,number]>(()=>area?[(Number(area.south)+Number(area.north))/2,(Number(area.west)+Number(area.east))/2]:point&&point.latitude&&point.longitude?[Number(point.latitude),Number(point.longitude)]:[47.1,19.2]);
  const [corner,setCorner]=useState<[number,number]|null>(null),[error,setError]=useState("");
  const [cx,cy]=mapPixel(...centre,zoom),left=cx-W/2,top=cy-H/2,tiles=[];
  for(let y=Math.floor(top/256);y<=Math.floor((top+H)/256);y++)for(let x=Math.floor(left/256);x<=Math.floor((left+W)/256);x++)if(y>=0&&y<2**zoom&&x>=0&&x<2**zoom)tiles.push({x,y});
  const position=(lat:number,lon:number)=>{const [x,y]=mapPixel(lat,lon,zoom);return [x-left,y-top];};
  const pan=(dx:number,dy:number)=>setCentre(mapCoordinate(cx+dx*W/3,cy+dy*H/3,zoom));
  const p=point&&point.latitude&&point.longitude?position(Number(point.latitude),Number(point.longitude)):null;
  const a=area?position(Number(area.north),Number(area.west)):null,b=area?position(Number(area.south),Number(area.east)):null;
  const c=corner?position(...corner):null;
  return <div className="space-y-2">
    <p>{mode==="area"?(corner?"Jelöld ki a körzet szemközti sarkát.":"Két kattintással jelöld ki a teljes edzési körzetet. A folyó kanyarulatai is legyenek benne."):"Kattints a tervezett edzés helyére."}</p>
    <div className="flex flex-wrap gap-2">{[["Nyugat",-1,0],["Kelet",1,0],["Észak",0,-1],["Dél",0,1]].map(([label,x,y])=><button key={String(label)} type="button" className={secondaryClass} onClick={()=>pan(Number(x),Number(y))}>{label}</button>)}
      <button type="button" className={secondaryClass} disabled={zoom>=13} onClick={()=>setZoom(z=>z+1)}>Nagyítás +</button><button type="button" className={secondaryClass} disabled={zoom<=4} onClick={()=>setZoom(z=>z-1)}>Kicsinyítés −</button>
      {corner&&<button type="button" className={secondaryClass} onClick={()=>setCorner(null)}>Kijelölés újrakezdése</button>}
    </div>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Edzéshelyszín és körzet kijelölése térképen" style={{width:"100%",background:"#dce5d5",cursor:"crosshair",borderRadius:8}} onClick={e=>{
      const bounds=e.currentTarget.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
      const v=mapCoordinate(left+(e.clientX-bounds.left)*W/bounds.width,top+(e.clientY-bounds.top)*H/bounds.height,zoom);
      setError("");
      if(mode==="point")onPoint({latitude:decimalDegree(v[0]),longitude:decimalDegree(v[1]),timezone_name:zone});
      else if(!corner)setCorner(v);else {
        const south=Math.min(corner[0],v[0]),north=Math.max(corner[0],v[0]),west=Math.min(corner[1],v[1]),east=Math.max(corner[1],v[1]);
        if(north-south<.000001||east-west<.000001||north-south>20||east-west>20){setError("Válassz nem üres, legfeljebb 20° széles és magas körzetet.");return;}
        onArea({schema_version:"training-area-v0.1",south:decimalDegree(south),north:decimalDegree(north),west:decimalDegree(west),east:decimalDegree(east),timezone_name:zone});setCorner(null);
      }
    }}>
      {tiles.map(t=><image key={`${zoom}/${t.x}/${t.y}`} href={`https://tile.openstreetmap.org/${zoom}/${t.x}/${t.y}.png`} x={t.x*256-left} y={t.y*256-top} width={256} height={256} />)}
      {a&&b&&<rect x={a[0]} y={a[1]} width={b[0]-a[0]} height={b[1]-a[1]} fill="#18a5b544" stroke="#087c8b" strokeWidth={3}/>}
      {p&&mode==="point"&&<circle cx={p[0]} cy={p[1]} r={7} fill="#ba2432" stroke="white" strokeWidth={2}/>}
      {c&&<circle cx={c[0]} cy={c[1]} r={6} fill="#087c8b"/>}
    </svg>
    <small>© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> közreműködők. A térképhez internetkapcsolat kell; a koordináták lent kézzel is megadhatók.</small>
    {error&&<p role="alert">{error}</p>}
  </div>;
}
