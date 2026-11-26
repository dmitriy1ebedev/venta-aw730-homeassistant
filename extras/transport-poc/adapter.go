// Package transport is a simulation-only contract. There is intentionally no
// socket, Tuya key, external dependency, HA integration or production entrypoint.
package transport

import (
 "encoding/json"
 "errors"
 "fmt"
 "sync"
)

var (
 ErrOffline = errors.New("offline: reconnect and read full state")
 ErrUnconfirmed = errors.New("write outcome unknown: do not replay")
 ErrInvalid = errors.New("invalid or unsupported DP")
 ErrStale = errors.New("stale session")
 ErrConflict = errors.New("command identifier already used")
)

type DP map[string]any
type Frame struct {
 Epoch uint64
 Data DP
}
type Command struct {
 ID string
 Values DP
}
type Result struct {
 Confirmed bool
 State DP
}
func clone(m DP) DP {
 n := DP{}
 for k,v := range m { n[k]=v }
 return n
}
func enum(v any, allowed ...string) bool {
 s,ok := v.(string)
 if !ok { return false }
 for _, a := range allowed { if a==s { return true } }
 return false
}
func integer(v any, lo, hi int) bool {
 i,ok := v.(int)
 return ok && i>=lo && i<=hi
}
func valid(k string,v any,write bool) bool {
 switch k {
 case "1","114": _,ok:=v.(bool); return ok
 case "13": return integer(v,30,70)
 case "24": return enum(v,"normal","automatic","sleep")
 case "105": return enum(v,"speed1","speed2","speed3","speed4","speed5")
 case "106": return enum(v,"bright1","bright2","bright3","bright4","bright5","bright6","bright7","bright8")
 case "14","102": return !write && integer(v,0,100)
 case "10": return !write && integer(v,-40,100)
 case "32","101","109","111": return !write && integer(v,0,1000000)
 }
 return false
}
var required = []string{"1","13","14","24","105","106","114"}

// FakeDevice is the only concrete backend. It models DP responses, not Tuya
// wire encryption, timing, firmware or actual connection limits.
type FakeDevice struct {
 mu sync.Mutex
 values DP
 epoch uint64
 online bool
 writes int
 fault string
}

func NewFake() *FakeDevice {
 return &FakeDevice{values:DP{"1":false,"13":50,"14":44,"24":"normal","105":"speed1","106":"bright4","114":true}}
}
func (d *FakeDevice) Inject(fault string) {
 d.mu.Lock(); defer d.mu.Unlock()
 d.fault=fault
}
func (d *FakeDevice) Writes() int {
 d.mu.Lock(); defer d.mu.Unlock()
 return d.writes
}
func (d *FakeDevice) connect() (Frame,error) {
 d.mu.Lock(); defer d.mu.Unlock()
 d.epoch++
 d.online=false
 if d.fault=="connect" { d.fault=""; return Frame{},ErrOffline }
 d.online=true
 f:=Frame{d.epoch,clone(d.values)}
 if d.fault=="missing" {delete(f.Data,"14");d.fault=""}
 return f,nil
}
func (d *FakeDevice) write(epoch uint64, values DP) (Frame,error) {
 d.mu.Lock(); defer d.mu.Unlock()
 if !d.online {return Frame{},ErrOffline}
 if epoch!=d.epoch {return Frame{},ErrStale}
 fault:=d.fault
 d.fault=""
 if fault=="before" {d.online=false;return Frame{},ErrUnconfirmed}
 d.writes++
 if fault!="ignore" {for k,v:=range values {d.values[k]=v}}
 if fault=="after" {d.online=false;return Frame{},ErrUnconfirmed}
 frame:=Frame{d.epoch,clone(d.values)}
 if fault=="stale" {frame.Epoch--}
 if fault=="missing" {delete(frame.Data,"14")}
 return frame,nil
}

// Adapter serializes one simulated writer; no timeout can trigger a replay.
// IDs are scoped to this in-memory adapter lifetime, not durable storage.
type Adapter struct {
 mu sync.Mutex
 device *FakeDevice
 epoch uint64
 ready bool
 state DP
 used map[string]string
}
func NewAdapter(d *FakeDevice) *Adapter {
 return &Adapter{device:d,used:map[string]string{}}
}
func snapshot(f Frame) (DP,error) {
 for _, k:=range required {
  if v,ok:=f.Data[k]; !ok || !valid(k,v,false) {return nil,ErrInvalid}
 }
 n:=DP{}
 for k,v:=range f.Data {if valid(k,v,false) {n[k]=v}}
 return n,nil
}
func (a *Adapter) Reconnect() error {
 a.mu.Lock();defer a.mu.Unlock()
 a.ready=false
 a.state=nil
 f,err:=a.device.connect()
 if err!=nil{return err}
 n,err:=snapshot(f)
 if err!=nil{return err}
 a.epoch=f.Epoch
 a.state=n
 a.ready=true
 return nil
}
func (a *Adapter) State() (DP,bool) {
 a.mu.Lock();defer a.mu.Unlock()
 if !a.ready {return nil,false}
 return clone(a.state),true
}
func (a *Adapter) invalidate() {
 a.ready=false
 a.state=nil
}
func (a *Adapter) Apply(c Command) (Result,error) {
 a.mu.Lock();defer a.mu.Unlock()
 if c.ID=="" || len(c.ID)>128 || len(c.Values)==0 || len(c.Values)>6 {return Result{},ErrInvalid}
 for k,v:=range c.Values {if !valid(k,v,true) {return Result{},ErrInvalid}}
 if c.Values["24"]=="automatic" {
  if _,ok:=c.Values["105"];ok{return Result{},ErrInvalid}
 }
 if c.Values["1"]==false && len(c.Values)>1 {return Result{},ErrInvalid}
 raw,err:=json.Marshal(c.Values)
 if err!=nil{return Result{},ErrInvalid}
 if _,exists:=a.used[c.ID];exists{return Result{},ErrConflict}
 if !a.ready {return Result{},ErrOffline}
 if _,ok:=c.Values["105"];ok {
  mode:=a.state["24"]
  if requested,exists:=c.Values["24"];exists {mode=requested}
  if mode!="normal" {return Result{},ErrInvalid}
 }
 if len(a.used)>=10000 {return Result{},fmt.Errorf("%w: simulation ID budget exhausted",ErrConflict)}
 a.used[c.ID]=string(raw)
 f,err:=a.device.write(a.epoch,c.Values)
 if err!=nil {a.invalidate();return Result{},ErrUnconfirmed}
 if f.Epoch!=a.epoch {a.invalidate();return Result{},ErrStale}
 n,err:=snapshot(f)
 if err!=nil {a.invalidate();return Result{},ErrUnconfirmed}
 for k,v:=range c.Values {
  if n[k]!=v {a.invalidate();return Result{},ErrUnconfirmed}
 }
 a.state=n
 return Result{true,clone(n)},nil
}
