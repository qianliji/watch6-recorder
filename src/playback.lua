-- One native lifecycle shared with archive preparation; never owns a second module.
local function create(archive)
 assert(type(archive)=='table' and type(archive.play)=='function','archive owner required')
 local out={}
 function out.play(info)return archive.play(info)end
 out.start=out.play
 function out.pause()return archive.pause()end
 function out.resume()return archive.resume()end
 function out.stop()return archive.stop()end
 function out.tick()return archive.tick()end
 function out.state()return archive.state()end
 function out.busy()return archive.busy()end
 function out.safe_to_record()return archive.safe_to_record()end
 function out.detach()end -- archive owns lifecycle; a view exit does not kill audio.
 return out
end
return create
