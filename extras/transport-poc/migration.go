package transport

import "errors"

// This contract accepts only a fixed public synthetic identity fixture.
// It neither reads nor writes Home Assistant registry/storage.
type Identity struct {
 ConfigEntry, Device, Entity, Bridge, Name, PairingFingerprint string
 ConfigEntries [4]string
 EntityBindings [7]string
 AID int
 IIDs [4]int
 AliceEntity string
}
type Fixture struct {
 Identity Identity
 Writer string
}
type Plan struct {
 Before Fixture
 After Fixture
}
var ErrMigration=errors.New("migration refused: synthetic identity or single-writer invariant")
func SyntheticFixture() Fixture {
 return Fixture{Identity:Identity{
 ConfigEntry:"fixture-entry",Device:"fixture-device",Entity:"humidifier.venta_fixture",
 Bridge:"fixture-bridge",Name:"Fixture Venta",PairingFingerprint:"synthetic-not-a-key",
 ConfigEntries:[4]string{"fixture-localtuya-entry","fixture-entry","fixture-bridge","fixture-yaha-entry"},
 EntityBindings:[7]string{"humidifier.venta_fixture","select.fixture_fan","switch.fixture_led","select.fixture_brightness","sensor.fixture_temperature","sensor.fixture_humidity","sensor.fixture_water"},
 AID:27,IIDs:[4]int{3,5,7,9},AliceEntity:"humidifier.venta_fixture",
 },Writer:"localtuya"}
}
func DryRun(f Fixture) (Plan,error) {
 if f!=SyntheticFixture(){return Plan{},ErrMigration}
 after:=f
 after.Writer="simulated"
 return Plan{Before:f,After:after},nil
}
// VentaState is a semantic read model, not a replacement HA entity.
// Optional readings are nil when absent or invalid, never invented zeros.
type VentaState struct {
 Power, LED bool
 TargetHumidity, CurrentHumidity, FanLevel, BrightnessLevel int
 Mode string
 Temperature, PM25, Water *int
}
type View struct {
 Identity Identity
 State *VentaState
}
func optionalInteger(d DP,k string) *int {
 if v,ok:=d[k].(int);ok{return &v}
 return nil
}
// Project exposes one known synthetic identity to all consumers. No registry
// changes or service dispatch. A nil State represents unavailable.
func Project(a *Adapter,f Fixture) (View,error) {
 plan,err:=DryRun(SyntheticFixture())
 if err!=nil || (f!=plan.Before && f!=plan.After) || a==nil{return View{},ErrMigration}
 v:=View{Identity:f.Identity}
 raw,ok:=a.State()
 if !ok{return v,nil}
 d,err:=snapshot(Frame{Data:raw})
 if err!=nil{return v,err}
 modes:=map[string]string{"normal":"Manual","automatic":"Auto","sleep":"Sleep"}
 fan,bright:=d["105"].(string),d["106"].(string)
 v.State=&VentaState{
  Power:d["1"].(bool),LED:d["114"].(bool),
  TargetHumidity:d["13"].(int),CurrentHumidity:d["14"].(int),
  FanLevel:int(fan[len(fan)-1]-'0'),BrightnessLevel:int(bright[len(bright)-1]-'0'),
  Mode:modes[d["24"].(string)],Temperature:optionalInteger(d,"10"),PM25:optionalInteger(d,"32"),Water:optionalInteger(d,"102"),
 }
 return v,nil
}
func (p Plan) Rollback(current Fixture) (Fixture,error) {
 expected,err:=DryRun(p.Before)
 if err!=nil || p!=expected || current!=p.After {return Fixture{},ErrMigration}
 return p.Before,nil
}
