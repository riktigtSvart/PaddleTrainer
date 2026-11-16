import type { ReactNode } from "react";

// Original code-native diagrams: no external image service or tracking pixels.
const drawings: Record<string, ReactNode> = {
  mat: (
    <>
      <path d="m23 64 78-39 40 23-78 39Z" fill="currentColor" opacity=".13" />
      <path d="m23 64 78-39 40 23-78 39Z M23 64v6l40 23 78-39v-6 M39 61l40 23 M55 53l40 23 M71 45l40 23 M87 37l40 23" />
    </>
  ),
  dumbbell: (
    <>
      <path d="M56 45h48v12H56z" fill="currentColor" opacity=".18" />
      <path d="M56 45h48v12H56z M32 27h13v49H32z M45 34h11v35H45z M104 34h11v35h-11z M115 27h13v49h-13z M26 50h6 M128 50h7" />
    </>
  ),
  barbell: (
    <>
      <path d="M16 50h128 M29 23h9v54h-9z M40 32h9v36h-9z M111 32h9v36h-9z M123 23h9v54h-9z" />
      <path d="M51 47h58v6H51z" fill="currentColor" opacity=".2" />
    </>
  ),
  ez_bar: (
    <>
      <path d="M17 51h31l12-12 16 23 15-23 14 12h39 M26 28h10v47H26z M125 28h10v47h-10z" />
    </>
  ),
  plates: (
    <>
      <circle cx="66" cy="50" r="31" />
      <circle cx="66" cy="50" r="8" />
      <circle cx="105" cy="57" r="25" fill="var(--pt-panel, transparent)" />
      <circle cx="105" cy="57" r="6" />
      <path d="M49 33a24 24 0 0 1 34 0 M88 72a20 20 0 0 0 30-4" />
    </>
  ),
  collars: (
    <>
      <ellipse cx="55" cy="49" rx="18" ry="25" />
      <ellipse cx="55" cy="49" rx="9" ry="16" />
      <path d="m66 30 17-11 8 12-18 12 M103 46h22v25h-22z M110 46V31h9v15" />
    </>
  ),
  kettlebell: (
    <>
      <path d="M58 39V27c0-21 44-21 44 0v12 M68 36v-8c0-9 24-9 24 0v8" />
      <path
        d="M60 36c-24 17-23 53 20 53s44-36 20-53Z"
        fill="currentColor"
        opacity=".16"
      />
      <path d="M60 36c-24 17-23 53 20 53s44-36 20-53Z" />
    </>
  ),
  trap_bar: (
    <>
      <path d="m53 22 54 0 23 28-23 28H53L30 50Z M48 34 64 50 48 66 M112 34 96 50l16 16 M12 50h18 M130 50h19 M18 30v40 M141 30v40" />
    </>
  ),
  sandbag: (
    <>
      <path
        d="M43 39c-9 7-9 37 0 43h76c9-6 9-36 0-43Z M52 40V25h18v15 M92 40V25h18v15 M55 45v31 M104 45v31"
        fill="currentColor"
        opacity=".13"
      />
      <path d="M43 39c-9 7-9 37 0 43h76c9-6 9-36 0-43Z M52 40V25h18v15 M92 40V25h18v15" />
    </>
  ),
  vest: (
    <>
      <path d="m51 15 20 7h18l20-7 11 27-16 8v38H56V50l-16-8Z M73 23v58 M87 23v58 M59 48h12v15H59z M90 48h12v15H90z M59 68h12v13H59z M90 68h12v13H90z" />
    </>
  ),
  bench: (
    <>
      <path d="M26 42h104v14H26z" fill="currentColor" opacity=".17" />
      <path d="M26 42h104v14H26z M47 56l-8 29 M111 56l9 29 M26 85h27 M107 85h27" />
    </>
  ),
  bench_press_station: (
    <>
      <path d="M37 48h86v13H37z" fill="currentColor" opacity=".17" />
      <path d="M37 48h86v13H37z M48 61v24 M111 61v24 M30 85h33 M102 85h29 M31 15v70 M128 15v70 M25 29h13v7H25z M121 29h13v7h-13z M16 24h128 M20 12v24 M137 12v24" />
    </>
  ),
  incline_bench: (
    <>
      <path
        d="m38 22 45 37-8 10-45-37Z M80 61h38v12H80z"
        fill="currentColor"
        opacity=".17"
      />
      <path d="m38 22 45 37-8 10-45-37Z M80 61h38v12H80z M76 70 58 88 M107 74l13 14 M45 89h26 M108 89h27" />
    </>
  ),
  box: (
    <>
      <path
        d="m39 32 48-13 35 20-47 16Z M39 32v43l36 20V55 M75 95l47-14V39 M48 48l17 9 M89 64l17-4"
        fill="currentColor"
        opacity=".12"
      />
      <path d="m39 32 48-13 35 20-47 16Z M39 32v43l36 20V55 M75 95l47-14V39" />
    </>
  ),
  pullup: (
    <>
      <path d="M35 89V19h90v70 M25 89h30 M108 89h30 M24 19h112 M36 24l19 12 M124 24l-19 12" />
    </>
  ),
  dip: (
    <>
      <path d="M29 87V37h46v50 M88 87V25h43v62 M24 87h20 M63 87h22 M81 87h20 M118 87h21" />
    </>
  ),
  suspension: (
    <>
      <path d="M80 12 46 69 M80 12l34 57 M34 70h25l-13 16Z M101 70h25l-12 16Z" />
      <circle cx="80" cy="13" r="5" />
    </>
  ),
  rings: (
    <>
      <path d="M56 13v45 M106 13v45" />
      <circle cx="56" cy="74" r="16" />
      <circle cx="106" cy="74" r="16" />
    </>
  ),
  anchor: (
    <>
      <path d="M50 16v72 M38 16h24 M38 88h24 M51 44h25l13 12-13 12H51 M89 56h35" />
      <circle cx="117" cy="56" r="14" />
    </>
  ),
  rack: (
    <>
      <path d="M33 90V13h94v77 M33 32h94 M33 68h94 M21 90h29 M111 90h28 M19 48h122 M43 26v4 M43 39v4 M43 56v4 M116 26v4 M116 39v4 M116 56v4" />
    </>
  ),
  smith: (
    <>
      <path d="M31 91V12h98v79 M47 21v61 M113 21v61 M21 91h30 M111 91h29 M29 48h103 M54 39v18 M105 39v18" />
    </>
  ),
  landmine: (
    <>
      <path d="M28 86h46 M51 85l63-66 M98 28l21 20 M107 19l21 20 M105 16l26 26" />
      <circle cx="51" cy="85" r="6" />
    </>
  ),
  cable: (
    <>
      <path d="M35 89V13h42v76 M24 89h67 M43 79h25 M43 71h25 M43 63h25 M43 55h25 M56 49V23h45v31l29 14 M118 69h24" />
      <circle cx="101" cy="23" r="7" />
    </>
  ),
  high_cable: (
    <>
      <path d="M33 90V14h40v76 M26 90h56 M42 68h21 M42 76h21 M54 62V22h52v31 M96 57h22" />
      <circle cx="106" cy="22" r="6" />
    </>
  ),
  low_cable: (
    <>
      <path d="M33 90V14h40v76 M26 90h56 M42 68h21 M42 76h21 M54 61v22h52l20-29 M116 52h22" />
      <circle cx="106" cy="83" r="6" />
    </>
  ),
  rope: (
    <>
      <path d="M80 19v28 M75 45 52 78 M85 45l23 33" />
      <circle cx="80" cy="19" r="8" />
      <circle cx="51" cy="80" r="7" />
      <circle cx="109" cy="80" r="7" />
    </>
  ),
  handle: (
    <>
      <path d="m80 22-32 47h64Z M48 69v10h64V69" />
      <circle cx="80" cy="22" r="6" />
    </>
  ),
  wide_bar: (
    <>
      <path d="m23 71 19-23h76l19 23 M43 49l-9 12 M117 49l9 12 M80 47V30" />
      <circle cx="80" cy="23" r="7" />
    </>
  ),
  ankle_cuff: (
    <>
      <ellipse cx="80" cy="57" rx="34" ry="22" />
      <path d="M46 57V35c0-25 68-25 68 0v22 M80 13v22 M91 14v22" />
      <circle cx="117" cy="47" r="10" />
    </>
  ),
  lat_machine: (
    <>
      <path d="M33 91V13h69v14 M23 91h86 M43 77h21 M43 69h21 M53 64V22h55v21 M86 47h45 M100 47v13 M86 64h35 M97 64v24 M80 89h47" />
    </>
  ),
  row_machine: (
    <>
      <path d="M29 89V18h38v71 M37 70h21 M37 78h21 M53 65v18h43 M96 80l12-28 M117 47h25v10h-25z M128 57v31 M117 88h29 M94 66h18" />
    </>
  ),
  press_machine: (
    <>
      <path d="M30 90V17h30v73 M38 70h15 M38 78h15 M90 27v39 M75 67h38v10H75z M90 77v13 M91 38l32-10 10 25 M118 53h20 M75 91h45" />
    </>
  ),
  shoulder_machine: (
    <>
      <path d="M32 90V15h30v75 M39 71h15 M39 79h15 M99 39v31 M82 71h36 M97 72v18 M83 90h40 M96 50 78 26 92 14 M105 50l22-24-10-12 M84 15h15 M112 15h15" />
    </>
  ),
  pec_machine: (
    <>
      <path d="M76 88V26 M61 70h31v10H61z M43 17v40l32 14 38-14V17 M35 17h16 M106 17h16 M63 88h30 M128 88V12h19v76" />
    </>
  ),
  leg_press: (
    <>
      <path d="m37 40 31 28-9 10-31-28Z M63 69h31 M41 77l-9 14 M96 80l32-55 M105 25l35 14 M90 88h49 M116 21l26 14" />
    </>
  ),
  leg_curl: (
    <>
      <path d="m35 29 31 37-9 8-31-37Z M65 68h34v11H65z M99 74l27-8 M120 61v14 M66 79v11 M48 90h40 M126 81h18V14h-18z" />
    </>
  ),
  leg_extension: (
    <>
      <path d="m35 29 31 37-9 8-31-37Z M65 68h34v11H65z M97 76l23 14 M116 81v14 M66 79v11 M48 90h40 M130 76h15V14h-15z" />
    </>
  ),
  hip_machine: (
    <>
      <path d="M80 21v42 M61 64h38v13H61z M80 78v13 M58 91h44 M80 70 45 51 33 72 M80 70l35-19 13 21 M27 70h19 M118 70h19" />
    </>
  ),
  back_extension: (
    <>
      <path d="m32 26 36 21-7 12-36-21Z M60 57l45 32 M51 90l48-45 M34 91h96 M94 43l23 13 M109 57l-9 9" />
    </>
  ),
  assisted_pullup: (
    <>
      <path d="M30 91V14h88v77 M18 16h112 M119 31h25v60h-25 M53 68h43v9H53z M76 77v14 M20 91h126" />
    </>
  ),
  band: (
    <>
      <ellipse cx="80" cy="52" rx="48" ry="23" transform="rotate(-25 80 52)" />
      <ellipse cx="80" cy="52" rx="38" ry="14" transform="rotate(-25 80 52)" />
    </>
  ),
  mini_band: (
    <>
      <path d="M48 31h64c29 0 29 43 0 43H48c-29 0-29-43 0-43Z M48 43h64c12 0 12 19 0 19H48c-12 0-12-19 0-19Z" />
    </>
  ),
  medicine_ball: (
    <>
      <circle cx="80" cy="52" r="33" fill="currentColor" opacity=".12" />
      <circle cx="80" cy="52" r="33" />
      <path d="M47 52h66 M80 19c-21 20-21 46 0 66 M80 19c21 20 21 46 0 66" />
    </>
  ),
  slam_ball: (
    <>
      <circle cx="80" cy="52" r="33" fill="currentColor" opacity=".15" />
      <circle cx="80" cy="52" r="33" />
      <path d="m60 35 4 2 M84 28l4 2 M99 42l3 2 M62 59l3 3 M83 66l3 3 M99 67l3 3" />
    </>
  ),
  swiss_ball: (
    <>
      <circle cx="80" cy="52" r="40" />
      <path
        d="M41 43h78 M40 54h80 M44 66h72 M51 78h58 M49 29h62"
        opacity=".45"
      />
    </>
  ),
  balance: (
    <>
      <path
        d="M28 70c0-61 104-61 104 0Z M22 72h116v10H22z"
        fill="currentColor"
        opacity=".15"
      />
      <path d="M28 70c0-61 104-61 104 0Z M22 72h116v10H22z" />
    </>
  ),
  roller: (
    <>
      <path d="M46 23h65c30 0 30 58 0 58H46 M55 24v56 M69 24v56 M83 24v56" />
      <ellipse cx="46" cy="52" rx="19" ry="29" />
      <ellipse cx="46" cy="52" rx="8" ry="14" />
    </>
  ),
  kayak_erg: (
    <>
      <path d="M24 86h116 M69 70V54h23v16 M49 71h66 M48 73l-8 13 M111 74l8 12 M55 43l58-21 M47 41l10-3 3 8-10 3Z M112 20l10-3 3 8-10 3Z M27 52l29-9 M27 52l57-20" />
      <circle cx="27" cy="65" r="15" />
    </>
  ),
  row_erg: (
    <>
      <circle cx="34" cy="55" r="23" />
      <circle cx="34" cy="55" r="13" />
      <path d="M50 70h88 M86 60h21v10H86z M69 62l-4-28 M66 35h19 M83 35l30-13 M114 17l6 12 M33 78l-9 12 M118 71l12 19" />
    </>
  ),
  bike: (
    <>
      <circle cx="49" cy="68" r="22" />
      <circle cx="108" cy="68" r="22" />
      <path d="m49 68 21-30 13 30H49l31-2 28-30v32 M63 36h20 M101 28h22 M108 28v9 M80 68l9 11 M86 79h12" />
    </>
  ),
  treadmill: (
    <>
      <path d="m26 75 89-16 25 16-89 16Z M111 58V22l21-9 M98 22h33v13H98z M36 84l-3 8 M130 82l7 10 M50 70l57-9" />
    </>
  ),
  ski_erg: (
    <>
      <path d="M36 92V12h80v80 M25 92h107 M48 21v43 M104 21v43 M39 66h20 M95 66h20 M65 92V59h23v33" />
      <circle cx="76" cy="75" r="12" />
    </>
  ),
};

// Machine diagrams share only the frame/load legend; their working arms and
// supports remain distinct. Plates and selectorized stacks look different.
function Station({
  children,
  plates = false,
}: {
  children: ReactNode;
  plates?: boolean;
}) {
  return (
    <>
      <path d="M22 94h128" opacity=".45" />
      {plates ? (
        <>
          <circle cx="139" cy="63" r="13" fill="currentColor" opacity=".15" />
          <circle cx="139" cy="63" r="13" />
          <circle cx="139" cy="63" r="4" />
          <path d="M122 63h17 M139 76v17" />
        </>
      ) : (
        <path d="M132 91V17h19v74z M137 38h9 M137 47h9 M137 56h9 M137 65h9 M137 74h9 M137 83h9" />
      )}
      {children}
    </>
  );
}
const machineParts: Record<string, ReactNode> = {
  supported_row: (
    <path d="M37 92V72h40 M59 69V38l13-6 8 29-13 4 M77 73l12 19 M83 31l29 22 M93 57h24 M111 53l-7 31 M31 93h57" />
  ),
  high_row_machine: (
    <path d="M34 92V13h87 M81 15l27 25-19 15 M100 40l-9 3 M48 52v22h37 M67 72v20 M41 92h51 M65 35v24" />
  ),
  pullover_machine: (
    <path d="M38 92V19h42 M79 20a27 27 0 0 1 23 41 M93 61h18 M73 45v30 M57 73h37 M75 75v17 M60 92h38 M88 39l-9 12" />
  ),
  reverse_pec_machine: (
    <path d="M79 89V27 M63 66h32v11H63z M36 19v36l42 16 39-16V19 M28 19h15 M109 19h16 M65 89h31 M70 33h18v18H70z" />
  ),
  lateral_raise_machine: (
    <path d="M76 32v38 M61 70h31v10H61z M75 81v11 M62 92h31 M76 63 42 39 28 49 M76 63l33-24 14 10 M31 45l12-12 M108 32l12 12" />
  ),
  biceps_machine: (
    <path d="M30 91V73h35 M48 69l20-28 18 13-20 28 M83 54l25 13 9-18 M105 47h18 M78 82v10 M62 92h35" />
  ),
  triceps_machine: (
    <path d="M31 92V74h31 M47 68l22-27 19 12-20 27 M83 54l27-16 9 10 M103 35l16 11 M78 81v11 M62 92h34" />
  ),
  dip_machine: (
    <path d="M69 29v42 M50 71h39v10H50z M70 81v11 M46 91h52 M43 37v23l-13 10 M94 37v23l15 10 M24 71h18 M101 71h18" />
  ),
  abdominal_machine: (
    <path d="M47 38v33 M38 73h40v10H38z M57 83v10 M36 93h48 M35 24l18-10 32 28-19 16 M79 45l24 12 M98 52l12 10 M93 58l-6 23" />
  ),
  torso_machine: (
    <path d="M45 89V65h46v24 M36 91h66 M67 65V27 M47 28h39v19H47z M43 48l24 12 25-12 M33 22a40 25 0 0 1 71 0 M96 15l9 9 8-6" />
  ),
  back_machine: (
    <path d="M38 92V69h40 M45 47l20-16 25 23 M77 46l19-19 12 9 M69 69l22-6 12 24 M81 90h30 M53 67l8-29" />
  ),
  seated_leg_curl: (
    <path d="M32 26v44h45v11H40 M78 74l31 2-17-26 M93 46h17 M63 81v11 M46 92h39 M75 59h24" />
  ),
  lying_leg_curl: (
    <path d="M28 60h41l14-9 29 9 M29 61v31 M106 62v30 M81 52l25-19 M101 27l13 10 M68 60l17 21 M81 78h15" />
  ),
  standing_calf: (
    <path d="M36 92V14h70v78 M57 25v45 M43 31h39v11H43z M43 77h43v10H43z M56 88v5 M31 94h80 M70 32l16 14" />
  ),
  seated_calf: (
    <path d="M35 91V68h35 M50 62h37v10H50z M79 63v29 M80 87h33 M73 43h40v10H73z M94 53v23 M104 75l20-12 M24 92h104" />
  ),
  glute_kickback: (
    <path d="M34 92V41l20-14 12 14 M55 43v31 M54 74l29 17 M80 93h29 M80 42l26 18-14 24 M99 55l15-12 M109 42l10 9" />
  ),
  glute_drive: (
    <path d="M28 52h31v15H28z M38 68v23 M63 71h35l18 18 M55 61l18-26 28 17 M72 34l-12 26 M113 89h14 M67 68l24-8 M35 92h92" />
  ),
  hack_squat: (
    <path d="M31 91 99 16 M45 91l66-75 M56 52l27 25 M74 32l28 24 M76 29l13-13 18 17 M34 82l26 12 M75 50l19 17" />
  ),
  belt_squat: (
    <path d="M29 82h84v10H29z M38 80V24h14 M98 80V24H84 M57 46h30l-6 14H62z M71 60v19 M75 78l39-15 M111 64h15" />
  ),
  tbar_row: (
    <path d="M32 92 90 23 M61 28l24 15-8 14-24-16Z M87 91l-8-35 M33 88l30-11 M55 75l45-39 M89 34l18 12 M102 42l19 16" />
  ),
  plate_lat: (
    <path d="M34 92V15h77 M85 15v25 M60 42h51 M87 44v25 M60 69h41v10H60z M78 80v12 M62 92h39 M60 56h42" />
  ),
  plate_press: (
    <path d="M44 27v44 M35 71h43v10H35z M56 82v11 M30 93h62 M81 64l23-31 15 12 M93 36l17 11 M84 59l18 12" />
  ),
  incline_press_machine: (
    <path d="M32 26l37 44-9 9-38-44Z M67 73h27 M66 78v15 M44 93h54 M73 49l22-31 16 11 M88 23l19 14 M78 53l26 16" />
  ),
  plate_shoulder: (
    <path d="M58 39v34 M40 73h41v10H40z M59 83v10 M41 93h45 M58 53 37 25 47 14 M67 53l35-28 13 13 M40 15h17 M108 32l12 12" />
  ),
  plate_leg_press: (
    <path d="m29 43 29 26-8 10-29-27Z M58 71h25 M36 79l-8 14 M84 79l30-55 M103 21l22 12 M80 93h48" />
  ),
  plate_leg_extension: (
    <path d="M33 27v42h45v11H42 M76 75l28 15 M98 81v14 M60 81v12 M44 93h43 M83 63l24-6" />
  ),
  plate_leg_curl: (
    <path d="M29 26v43h45v11H40 M74 73l29-7 M99 60v14 M59 81v12 M44 93h43 M80 50l29-9" />
  ),
  decline_press_machine: (
    <path d="m31 54 50 20-6 12-50-20Z M43 74l-8 18 M71 85v8 M81 53l23-15 13 15 M98 39l17 14 M75 61l24 12 M30 93h80" />
  ),
};
const variants: Record<string, [string, boolean]> = {
  supported_row: ["supported_row", false],
  high_row_machine: ["high_row_machine", false],
  pullover_machine: ["pullover_machine", false],
  reverse_pec_machine: ["reverse_pec_machine", false],
  lateral_raise_machine: ["lateral_raise_machine", false],
  biceps_machine: ["biceps_machine", false],
  triceps_machine: ["triceps_machine", false],
  dip_machine: ["dip_machine", false],
  abdominal_machine: ["abdominal_machine", false],
  torso_machine: ["torso_machine", false],
  back_machine: ["back_machine", false],
  seated_leg_curl: ["seated_leg_curl", false],
  lying_leg_curl: ["lying_leg_curl", false],
  standing_calf: ["standing_calf", false],
  seated_calf: ["seated_calf", true],
  glute_kickback: ["glute_kickback", false],
  glute_drive: ["glute_drive", true],
  hack_squat: ["hack_squat", true],
  belt_squat: ["belt_squat", true],
  tbar_row: ["tbar_row", true],
  plate_row: ["supported_row", true],
  plate_lat: ["plate_lat", true],
  plate_press: ["plate_press", true],
  incline_press_machine: ["incline_press_machine", true],
  plate_shoulder: ["plate_shoulder", true],
  plate_leg_press: ["plate_leg_press", true],
  plate_leg_extension: ["plate_leg_extension", true],
  plate_leg_curl: ["plate_leg_curl", true],
  plate_pullover: ["pullover_machine", true],
  plate_high_row: ["high_row_machine", true],
  decline_press_machine: ["decline_press_machine", true],
  plate_lateral_raise: ["lateral_raise_machine", true],
  plate_biceps: ["biceps_machine", true],
};
for (const [key, [parts, plates]] of Object.entries(variants)) {
  drawings[key] = <Station plates={plates}>{machineParts[parts]}</Station>;
}
drawings.seal_row_bench = (
  <>
    <path d="M24 24h112v13H24z M43 38v53 M117 38v53 M30 92h30 M105 92h27 M18 67h124 M27 55v24 M36 58v18 M125 55v24 M116 58v18 M66 86v7h22v-7" />
    <path d="M24 24h112v13H24z" fill="currentColor" opacity=".15" />
  </>
);
drawings.preacher_bench = (
  <>
    <path d="M40 83v10 M25 73h37v10H25z M46 67l28-36 22 15-29 36Z M80 68v24 M66 93h39 M28 93h33 M91 56l24 16 M104 66l15 9" />
    <path d="m74 31 22 15-9 13-22-15Z" fill="currentColor" opacity=".15" />
  </>
);
drawings.situp_bench = (
  <>
    <path d="m30 64 84-31 5 13-84 31Z M44 76v16 M103 48v44 M31 93h30 M90 93h30 M114 34V15 M103 16h25 M104 28h24" />
    <path d="m30 64 84-31 5 13-84 31Z" fill="currentColor" opacity=".15" />
  </>
);

drawings.wall_bars = (
  <>
    <path d="M38 12v80 M116 12v80 M38 16h78 M38 28h78 M38 40h78 M38 52h78 M38 64h78 M38 76h78 M38 88h78 M117 23h18v-9 M117 77h18v13" />
    <path d="M38 16h78v72H38z" fill="currentColor" opacity=".07" />
  </>
);
drawings.pullup_frame = (
  <>
    <path d="M26 20h108 M43 20 27 91 M117 20l16 71 M43 20v71 M117 20v71 M18 92h41 M103 92h40 M31 72h12 M117 72h12" />
    <path d="M48 19h64v4H48z" fill="currentColor" opacity=".2" />
  </>
);

export default function EquipmentIllustration({ kind }: { kind: string }) {
  return (
    <svg
      viewBox="0 0 160 104"
      className="pt-equipment-illustration"
      aria-hidden="true"
      focusable="false"
    >
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {drawings[kind] ?? (
          <>
            <circle cx="80" cy="52" r="32" />
            <path d="M68 39c0-18 28-18 28 0 0 12-16 12-16 23 M80 73v1" />
          </>
        )}
      </g>
    </svg>
  );
}
export const equipmentIllustrationIds = Object.keys(drawings);
