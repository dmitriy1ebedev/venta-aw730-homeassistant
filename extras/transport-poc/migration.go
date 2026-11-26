package transport

import "errors"

// This contract accepts only a fixed public synthetic identity fixture.
// It neither reads nor writes Home Assistant registry/storage.
type Identity struct {
 ConfigEntry, Device, Entity, Bridge, Name, PairingFingerprint string
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
 AID:27,IIDs:[4]int{3,5,7,9},AliceEntity:"humidifier.venta_fixture",
 },Writer:"localtuya"}
}
func DryRun(f Fixture) (Plan,error) {
 if f!=SyntheticFixture(){return Plan{},ErrMigration}
 after:=f
 after.Writer="simulated"
 return Plan{Before:f,After:after},nil
}
func (p Plan) Rollback(current Fixture) (Fixture,error) {
 expected,err:=DryRun(p.Before)
 if err!=nil || p!=expected || current!=p.After {return Fixture{},ErrMigration}
 return p.Before,nil
}
