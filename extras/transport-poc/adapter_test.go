package transport

import (
 "errors"
 "fmt"
 "sync"
 "testing"
)

func ready(t testing.TB) (*Adapter,*FakeDevice) {
 t.Helper()
 d:=NewFake()
 a:=NewAdapter(d)
 if err:=a.Reconnect();err!=nil {t.Fatal(err)}
 return a,d
}
func TestReadbackAndCommands(t *testing.T) {
 a,d:=ready(t)
 for i,c:=range []DP{{"1":true},{"13":70},{"24":"automatic"},{"24":"sleep"},{"24":"normal","105":"speed5"},{"106":"bright8","114":false},{"1":false}} {
  r,err:=a.Apply(Command{fmt.Sprint(i),c})
  if err!=nil || !r.Confirmed {t.Fatal(i,err)}
  for k,v:=range c {if r.State[k]!=v {t.Fatal("bad readback",k)}}
  r.State["13"]=0
  s,_:=a.State();if s["13"]==0 {t.Fatal("state alias")}
 }
 if d.Writes()!=7 {t.Fatal(d.Writes())}
}
func TestInvalidNeverWrites(t *testing.T) {
 a,d:=ready(t)
 for i,c:=range []DP{{"28":true},{"104":true},{"108":true},{"14":50},{"13":71},{"13":float64(40)},{"1":"true"},{"105":"speed6"},{"106":"bright9"},{"24":"auto"},{"24":"automatic","105":"speed2"},{"1":false,"24":"normal"},{"999":true}} {
  if _,err:=a.Apply(Command{fmt.Sprint(i),c});!errors.Is(err,ErrInvalid){t.Fatalf("%v %v",c,err)}
 }
 if d.Writes()!=0 {t.Fatal("invalid write")}
}
func TestManualSpeedRequiresManualMode(t *testing.T) {
 a,d:=ready(t)
 if _,err:=a.Apply(Command{"auto",DP{"24":"automatic"}});err!=nil{t.Fatal(err)}
 if _,err:=a.Apply(Command{"speed",DP{"105":"speed2"}});!errors.Is(err,ErrInvalid){t.Fatal(err)}
 if d.Writes()!=1{t.Fatal("conflicting speed dispatched")}
 if _,err:=a.Apply(Command{"manual",DP{"24":"normal","105":"speed2"}});err!=nil{t.Fatal(err)}
}
func TestUnknownNeverReplayAndReconnect(t *testing.T) {
 for _,fault:=range []string{"before","after","ignore","stale","missing"} {
  t.Run(fault,func(t *testing.T){
   a,d:=ready(t);d.Inject(fault)
   c:=Command{"once",DP{"13":60}}
   r,err:=a.Apply(c)
   if err==nil || r.Confirmed {t.Fatal("false confirmation")}
   if _,ok:=a.State();ok {t.Fatal("stale state marked ready")}
   n:=d.Writes()
   if _,err=a.Apply(c);!errors.Is(err,ErrConflict){t.Fatal(err)}
   if _,err=a.Apply(Command{"new",DP{"13":55}});!errors.Is(err,ErrOffline){t.Fatal(err)}
   if d.Writes()!=n {t.Fatal("replay")}
   if err=a.Reconnect();err!=nil {t.Fatal(err)}
   s,ok:=a.State();if !ok {t.Fatal("no snapshot")}
   want:=50;if fault=="after"||fault=="stale"||fault=="missing"{want=60}
   if s["13"]!=want {t.Fatalf("readback %v want %v",s,want)}
   if _,err=a.Apply(c);!errors.Is(err,ErrConflict){t.Fatal(err)}
   if d.Writes()!=n {t.Fatal("replay after reconnect")}
  })
 }
}
func TestReconnectRequiresCompleteSnapshot(t *testing.T) {
 a,d:=ready(t)
 for _,f:=range []string{"connect","missing"} {
  d.Inject(f);if err:=a.Reconnect();err==nil {t.Fatal("accepted",f)}
  if _,ok:=a.State();ok {t.Fatal("stale availability")}
  if err:=a.Reconnect();err!=nil {t.Fatal(err)}
 }
}
func TestTwoAdaptersFenceOldSession(t *testing.T) {
 a,d:=ready(t)
 b:=NewAdapter(d);if err:=b.Reconnect();err!=nil{t.Fatal(err)}
 if r,err:=a.Apply(Command{"old",DP{"1":true}});err==nil||r.Confirmed{t.Fatal("old session wrote")}
 if d.Writes()!=0{t.Fatal("old writer dispatched")}
 if r,err:=b.Apply(Command{"new",DP{"1":true}});err!=nil||!r.Confirmed{t.Fatal(err)}
}
func TestConcurrentDuplicate(t *testing.T) {
 a,d:=ready(t);var wg sync.WaitGroup
 for i:=0;i<20;i++ {wg.Add(1);go func(){defer wg.Done();_,_ = a.Apply(Command{"same",DP{"1":true}})}()}
 wg.Wait();if d.Writes()!=1{t.Fatal(d.Writes())}
}
func TestMigrationIdentityAndRollback(t *testing.T) {
 original:=SyntheticFixture()
 p,err:=DryRun(original);if err!=nil {t.Fatal(err)}
 if p.After.Identity!=original.Identity || p.After.Writer!="simulated" || original.Writer!="localtuya"{t.Fatal("identity drift")}
 restored,err:=p.Rollback(p.After);if err!=nil||restored!=original{t.Fatal("rollback",err)}
 changed:=p.After;changed.Identity.AID++
 if _,err=p.Rollback(changed);!errors.Is(err,ErrMigration){t.Fatal(err)}
 changed=original;changed.Identity.Name="renamed"
 if _,err=DryRun(changed);!errors.Is(err,ErrMigration){t.Fatal(err)}
 p.After.Identity.IIDs[0]++
 if _,err=p.Rollback(p.After);!errors.Is(err,ErrMigration){t.Fatal(err)}
}
func BenchmarkSimulatedCommandReadback(b *testing.B) {
 a,_:=ready(b)
 for i:=0;i<b.N;i++ {
  if i>0&&i%9000==0{a,_=ready(b)}
  if _,err:=a.Apply(Command{fmt.Sprint(i),DP{"13":30+i%41}});err!=nil{b.Fatal(err)}
 }
}
func BenchmarkSimulatedReconnect(b *testing.B) {
 a,_:=ready(b)
 for i:=0;i<b.N;i++ {if err:=a.Reconnect();err!=nil{b.Fatal(err)}}
}
