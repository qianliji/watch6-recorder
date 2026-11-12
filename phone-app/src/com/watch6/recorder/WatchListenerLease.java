package com.watch6.recorder;

/** One serialized SDK listener slot across service generations and bridge instances.
 * Calls and callbacks run on the main handler. A stale successful add still owns
 * a real SDK resource, so it is removed before the next owner can register.
 */
final class WatchListenerLease {
    interface Result { void complete(Exception error); }
    interface Port { void add(String node, Result result); void remove(String node, Result result); }
    interface Post { void later(Runnable runnable,long delay); }
    interface Clock { long now(); }
    interface Completion { void ready(); void failed(Exception error); }
    private static final class Target {
        final Object owner;
        final long generation;
        final String node;
        final Port port;
        final Post post;
        final Completion completion;
        long settleProof;
        int settleRetries;
        Target(Object owner,long generation,String node,Port port,Post post,Completion completion) {
            this.owner=owner;this.generation=generation;this.node=node;this.port=port;this.post=post;this.completion=completion;
        }
    }
    private Target desired, installed, operation;
    private final Clock clock;
    private String removedNode;
    private long removedAt,removeProof;
    WatchListenerLease(Clock clock){this.clock=clock;}

    void acquire(Object owner,long generation,String node,Port port,Post post,Completion completion) {
        desired=new Target(owner,generation,node,port,post,completion);
        armSettle(desired);
        drain();
    }

    void release(Object owner) {
        if(desired!=null&&desired.owner==owner)desired=null;
        drain();
    }

    private void drain() {
        if(operation!=null)return;
        if(installed!=null) {
            if(installed==desired)return;
            final Target target=installed;
            operation=target;
            try { target.port.remove(target.node,error->target.post.later(()->removed(target,error),0)); }
            catch(Exception error) { target.post.later(()->removed(target,error),0); }
            return;
        }
        if(desired==null)return;
        final Target target=desired;
        operation=target;
        try { target.port.add(target.node,error->target.post.later(()->added(target,error),0)); }
        catch(Exception error) { target.post.later(()->added(target,error),0); }
    }

    private boolean settling(Target target){
        long elapsed=clock.now()-removedAt;
        return removeProof!=0&&target.node.equals(removedNode)&&elapsed>=0&&elapsed<=100;
    }
    private void armSettle(Target target){
        if(settling(target)){target.settleProof=removeProof;target.settleRetries=4;}
    }

    private void added(Target target,Exception error) {
        if(operation!=target)return;
        operation=null;
        if(error instanceof IllegalStateException&&"you have registered".equals(error.getMessage())
                &&desired==target&&target.settleRetries>0&&target.settleProof==removeProof&&settling(target)){
            // SDK 1.4 publishes remove Task success just before clearing its
            // volatile slot. Only retry add, never remove an unknown owner.
            target.settleRetries--;operation=target;
            target.post.later(()->{if(operation!=target)return;operation=null;drain();},25);
            return;
        }
        if(error==null)installed=target;
        if(desired==target) {
            if(error==null)target.completion.ready();
            else { desired=null;target.completion.failed(error); }
        }
        drain();
    }

    private void removed(Target target,Exception error) {
        if(operation!=target)return;
        operation=null;
        if(error!=null) {
            // Retain the known slot after a failed removal. A later explicit
            // acquisition can retry; never race a second add into that slot.
            Target waiting=desired;
            desired=null;
            if(waiting!=null)waiting.completion.failed(error);
            return;
        }
        installed=null;
        removedNode=target.node;removedAt=clock.now();removeProof++;
        if(desired!=null)armSettle(desired);
        drain();
    }
}
