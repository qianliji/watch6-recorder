const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const toolkit=process.env.W6R_AIOT_TOOLKIT;
const signer=process.env.W6R_RPK_SIGNER||path.join(__dirname,'sign/release');
if(!toolkit)throw new Error('Set W6R_AIOT_TOOLKIT to the authorized local aiot-toolkit');
const {default:Builder}=require(path.join(toolkit,'lib/builder/VelaUxBuilder'));
const builder=new Builder();
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
(async()=>{
  const started=Date.now();
  const stage=path.join(__dirname,'build-runs','run-'+started+'-'+crypto.randomBytes(4).toString('hex'));
  const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'src/manifest.json'),'utf8'));
  if(manifest.package!=='com.watch6.recorder'||manifest.versionCode<5)throw new Error('Identity package or upgrade version is invalid');
  if(JSON.stringify(manifest.features)!==JSON.stringify([{name:'system.interconnect'}]))throw new Error('Identity may only declare system.interconnect');
  const name=manifest.package+'.release.'+manifest.versionName+'.rpk',inputs={};
  function copy(relative){
    const from=path.join(__dirname,relative),to=path.join(stage,relative),stat=fs.lstatSync(from);
    if(stat.isSymbolicLink())throw new Error('Linked build source rejected');
    if(stat.isDirectory()){fs.mkdirSync(to,{recursive:true});for(const n of fs.readdirSync(from).sort())copy(path.join(relative,n));}
    else{const bytes=fs.readFileSync(from);fs.mkdirSync(path.dirname(to),{recursive:true});fs.writeFileSync(to,bytes);inputs[relative.split(path.sep).join('/')]=sha(bytes);}
  }
  copy('src');copy('package.json');
  try{
    await builder.build(stage,{mode:'production',signRequest:async()=>({privatekey:fs.readFileSync(path.join(signer,'private.pem')),certificate:fs.readFileSync(path.join(signer,'certificate.pem'))})});
    const output=path.join(stage,'dist',name);
    if(!fs.existsSync(output)||fs.statSync(output).mtimeMs<started)throw new Error('Toolkit did not produce a fresh identity RPK');
    for(const [relative,hash]of Object.entries(inputs))if(sha(fs.readFileSync(path.join(__dirname,relative)))!==hash)throw new Error('Build input changed during compilation');
    const bytes=fs.readFileSync(output),certificate=new crypto.X509Certificate(fs.readFileSync(path.join(signer,'certificate.pem')));
    if(!bytes.includes(certificate.raw))throw new Error('RPK does not embed the expected public signing certificate');
    const report={version:manifest.versionName,version_code:manifest.versionCode,package:manifest.package,name:manifest.name,bytes:bytes.length,sha256:sha(bytes),certificate_sha256:sha(certificate.raw),signer_certificate_der_embedded:true,source_inputs:inputs,build_script_sha256:sha(fs.readFileSync(__filename)),toolkit_version:JSON.parse(fs.readFileSync(path.join(toolkit,'package.json'),'utf8')).version,role:'MiFitness communication identity only; recording and playback live in the watchface',native_payload:false,microphone_api:false,physical_verified:false};
    fs.mkdirSync(path.join(__dirname,'dist'),{recursive:true});fs.copyFileSync(output,path.join(__dirname,'dist',name));
    fs.writeFileSync(path.join(__dirname,'dist/build-report-'+manifest.versionName+'.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({passed:true,version:report.version,version_code:report.version_code,bytes:report.bytes,sha256:report.sha256,certificate_sha256:report.certificate_sha256,physical_verified:false}));
  }finally{await builder.dispose();}
})().catch(error=>{let message=String(error.message);for(const value of [toolkit,signer])message=message.split(value).join('<local build input>');console.error(message);process.exitCode=1;});
