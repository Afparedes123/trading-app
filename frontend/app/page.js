"use client"
import { useEffect, useState } from 'react'
export default function Home(){ const [s,setS]=useState([]); useEffect(()=>{fetch('http://localhost:8000/signals/live').then(r=>r.json()).then(setS)},[]); return <div>{s.map((x,i)=><div key={i}>{x.ticker}</div>)}</div> }
