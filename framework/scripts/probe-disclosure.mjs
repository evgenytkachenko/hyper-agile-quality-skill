// Explicit diagnostic of the isolated seeded defect; never a production target.
import {createVulnerableServer} from '../benchmarks/missing-authorization/server.ts';
const server=createVulnerableServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
try{
 const r=await fetch(`http://127.0.0.1:${server.address().port}/api/labs/lab-b`,{headers:{Authorization:'Bearer demo-session-a'}});
 const body=await r.json();const observation={status:r.status,requestedAs:'patient-a',returnedPatient:body.patientId,returnedLab:body.id};
 console.log(JSON.stringify(observation));
 if(r.status!==200||body.patientId!=='patient-b'||body.id!=='lab-b')process.exitCode=1;
}finally{await new Promise((r,j)=>server.close(e=>e?j(e):r()));}
