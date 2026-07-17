
function getSysData(){
    
    
    $.ajax({
           type: "GET",
           url: '/getSysdata/',
           dataType: "json",
           
           success:function(data){
               updateData(data);
           }

            }); 
    
   
}

var charts = [];


function updateData(data){
        
        var running = Boolean(data.Experiment.ON); //True if Experiment is running.
		
		
		 	
		
         
				
		  
        // Update Terminal        
        document.getElementById("termI").innerHTML=data.Terminal.text;
        
        //Update Output Indicators
        document.getElementById("LEDADefault").innerHTML=data.LEDA.default.toFixed(3);
        document.getElementById("LEDACurrent").innerHTML=data.LEDA.target.toFixed(3);
        document.getElementById("LEDBDefault").innerHTML=data.LEDB.default.toFixed(3);
        document.getElementById("LEDBCurrent").innerHTML=data.LEDB.target.toFixed(3);
        document.getElementById("LEDCDefault").innerHTML=data.LEDC.default.toFixed(3);
        document.getElementById("LEDCCurrent").innerHTML=data.LEDC.target.toFixed(3);
        document.getElementById("LEDDDefault").innerHTML=data.LEDD.default.toFixed(3);
        document.getElementById("LEDDCurrent").innerHTML=data.LEDD.target.toFixed(3);
        document.getElementById("LEDEDefault").innerHTML=data.LEDE.default.toFixed(3);
        document.getElementById("LEDECurrent").innerHTML=data.LEDE.target.toFixed(3);
        document.getElementById("LEDFDefault").innerHTML=data.LEDF.default.toFixed(3);
        document.getElementById("LEDFCurrent").innerHTML=data.LEDF.target.toFixed(3);
        document.getElementById("LEDGDefault").innerHTML=data.LEDG.default.toFixed(3);
        document.getElementById("LEDGCurrent").innerHTML=data.LEDG.target.toFixed(3);

        document.getElementById("LEDHDefault").innerHTML=data.LEDH.default.toFixed(3);
        document.getElementById("LEDHCurrent").innerHTML=data.LEDH.target.toFixed(3);
        document.getElementById("LEDIDefault").innerHTML=data.LEDI.default.toFixed(3);
        document.getElementById("LEDICurrent").innerHTML=data.LEDI.target.toFixed(3);
        document.getElementById("LEDVDefault").innerHTML=data.LEDV.default.toFixed(3);
        document.getElementById("LEDVCurrent").innerHTML=data.LEDV.target.toFixed(3);

        document.getElementById("UVDefault").innerHTML=data.UV.default.toFixed(3);
        document.getElementById("UVCurrent").innerHTML=data.UV.target.toFixed(3);
        
        
        document.getElementById("LASER650Default").innerHTML=data.LASER650.default.toFixed(3);
        document.getElementById("LASER650Current").innerHTML=data.LASER650.target.toFixed(3);
        
        document.getElementById("Pump1Current").innerHTML=data.Pump1.target.toFixed(3);
        document.getElementById("Pump2Current").innerHTML=data.Pump2.target.toFixed(3);
        
        document.getElementById("Pump3Current").innerHTML=data.Pump3.target.toFixed(3);
        document.getElementById("Pump4Current").innerHTML=data.Pump4.target.toFixed(3);
        
        
        document.getElementById("StirCurrent").innerHTML=data.Stir.target.toFixed(3);
        document.getElementById("LightCurrent").innerHTML=data.Light.Excite;
        document.getElementById("CustomStatus").innerHTML=data.Custom.Status.toFixed(3);
        
         
        document.getElementById("StartTime").innerHTML = data.Experiment.startTime;
        
        
        
        document.getElementById("410nmSense").innerHTML = data.AS7341.spectrum.nm410.toFixed(0);
        document.getElementById("440nmSense").innerHTML = data.AS7341.spectrum.nm440.toFixed(0);
        document.getElementById("470nmSense").innerHTML = data.AS7341.spectrum.nm470.toFixed(0);
        document.getElementById("510nmSense").innerHTML = data.AS7341.spectrum.nm510.toFixed(0);
        document.getElementById("550nmSense").innerHTML = data.AS7341.spectrum.nm550.toFixed(0);
        document.getElementById("583nmSense").innerHTML = data.AS7341.spectrum.nm583.toFixed(0);
        document.getElementById("620nmSense").innerHTML = data.AS7341.spectrum.nm620.toFixed(0);
        document.getElementById("670nmSense").innerHTML = data.AS7341.spectrum.nm670.toFixed(0);
        document.getElementById("ClearSense").innerHTML = data.AS7341.spectrum.CLEAR.toFixed(0);
        
        document.getElementById("FPBase1Value").innerHTML = data.FP1.Base.toFixed(0);
        document.getElementById("FPEmit1AValue").innerHTML = data.FP1.Emit1.toFixed(3);
        document.getElementById("FPEmit1BValue").innerHTML = data.FP1.Emit2.toFixed(3);
        
        document.getElementById("FPBase2Value").innerHTML = data.FP2.Base.toFixed(0);
        document.getElementById("FPEmit2AValue").innerHTML = data.FP2.Emit1.toFixed(3);
        document.getElementById("FPEmit2BValue").innerHTML = data.FP2.Emit2.toFixed(3);
        
        document.getElementById("FPBase3Value").innerHTML = data.FP3.Base.toFixed(0);
        document.getElementById("FPEmit3AValue").innerHTML = data.FP3.Emit1.toFixed(3);
        document.getElementById("FPEmit3BValue").innerHTML = data.FP3.Emit2.toFixed(3);
        
        
        document.getElementById("TName").innerHTML = "Device: " + data.UIDevice
        document.getElementById("TempCurrent").innerHTML = data.ThermometerExternal.current.toFixed(3);
        document.getElementById("TempCurrent2").innerHTML = data.ThermometerInternal.current.toFixed(3);
        document.getElementById("TempCurrent3").innerHTML = data.ThermometerIR.current.toFixed(3);
        document.getElementById("ThermostatTarget").innerHTML=data.Thermostat.target.toFixed(3);
        
        
        document.getElementById("ODCurrent").innerHTML = data.OD.current.toFixed(3);
        
        document.getElementById("OD0Current").innerHTML = data.OD0.target.toFixed(0);
        document.getElementById("ODRaw").innerHTML = data.OD0.raw.toFixed(0);
        
        document.getElementById("VolumeCurrent").innerHTML = data.Volume.target.toFixed(3);
        
        document.getElementById("ODTarget").innerHTML = data.OD.target.toFixed(3);
        
           
        // Do Experiment-dependent things
       
        
        if (running){
             document.getElementById("ExperimentRunningIndicator").setAttribute("class", "btn btn-success")
             document.getElementById("ExperimentRunningIndicator").innerHTML= "&nbsp &nbsp &nbsp   Running   &nbsp &nbsp &nbsp"
        } else {
             document.getElementById("ExperimentRunningIndicator").setAttribute("class", "btn btn-danger")
             document.getElementById("ExperimentRunningIndicator").innerHTML=  "&nbsp &nbsp &nbsp   Stopped   &nbsp &nbsp &nbsp"
        }
        


        document.getElementById("ExperimentStart").disabled = running;
        document.getElementById("ExperimentReset").disabled = running;
        document.getElementById("ExperimentStop").disabled = !running;
        
        var measuring = Boolean(data.OD.Measuring); //True if we are measuring things

        
        
        document.getElementById("LEDASwitch").disabled = (measuring );
        document.getElementById("LEDBSwitch").disabled = (measuring );
        document.getElementById("LEDCSwitch").disabled = (measuring );
        document.getElementById("LEDDSwitch").disabled = (measuring );
        document.getElementById("LEDESwitch").disabled = (measuring );
        document.getElementById("LEDFSwitch").disabled = (measuring );
        document.getElementById("LEDGSwitch").disabled = (measuring );
        document.getElementById("LEDHSwitch").disabled = (measuring );
        document.getElementById("LEDISwitch").disabled = (measuring );
        document.getElementById("LEDVSwitch").disabled = (measuring );
        document.getElementById("LASER650Switch").disabled = (measuring );
        
        document.getElementById("GetSpectrum").disabled = (measuring );
        
        document.getElementById("TempMeasure").disabled = (measuring );
        document.getElementById("TempMeasure2").disabled = (measuring );
        document.getElementById("TempMeasure3").disabled = (measuring );
        document.getElementById("ODMeasure").disabled = (measuring );
        
        
        
        
        
        
    
    
    
        
        
         if (data.LEDA.ON==1.0){
             document.getElementById("LEDASwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDASwitch").setAttribute("style", "")
        }
        
        
        if (data.LEDB.ON==1){
             document.getElementById("LEDBSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDBSwitch").setAttribute("style", "")
        }
        
        if (data.LEDC.ON==1){
             document.getElementById("LEDCSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDCSwitch").setAttribute("style", "")
        }
        if (data.LEDD.ON==1){
             document.getElementById("LEDDSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDDSwitch").setAttribute("style", "")
        }
        if (data.LEDE.ON==1){
             document.getElementById("LEDESwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDESwitch").setAttribute("style", "")
        }
        if (data.LEDF.ON==1){
             document.getElementById("LEDFSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDFSwitch").setAttribute("style", "")
        }
        if (data.LEDG.ON==1){
             document.getElementById("LEDGSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LEDGSwitch").setAttribute("style", "")
        }
        
        if (data.LEDH.ON==1){
          document.getElementById("LEDHSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
          
     } else {
          document.getElementById("LEDHSwitch").setAttribute("style", "")
     }

     if (data.LEDI.ON==1){
          document.getElementById("LEDISwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
          
     } else {
          document.getElementById("LEDISwitch").setAttribute("style", "")
     }

     if (data.LEDV.ON==1){
          document.getElementById("LEDVSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
          
     } else {
          document.getElementById("LEDVSwitch").setAttribute("style", "")
     }


        
         if (data.UV.ON==1){
             document.getElementById("UVSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("UVSwitch").setAttribute("style", "")
        }
        
        
        if (data.FP1.ON==1){
             document.getElementById("FP1Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             document.getElementById("FPExcite1").disabled = 1
             document.getElementById("FPBase1").disabled = 1
             document.getElementById("FPEmit1A").disabled = 1
             document.getElementById("FPEmit1B").disabled = 1
             document.getElementById("FPGain1").disabled = 1
        } else {
             document.getElementById("FP1Switch").setAttribute("style", "")
             document.getElementById("FPExcite1").disabled = 0
             document.getElementById("FPBase1").disabled = 0
             document.getElementById("FPEmit1A").disabled = 0
             document.getElementById("FPEmit1B").disabled = 0
             document.getElementById("FPGain1").disabled = 0
        }
        
        if (data.FP2.ON==1){
             document.getElementById("FP2Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             document.getElementById("FPExcite2").disabled = 1
             document.getElementById("FPBase2").disabled = 1
             document.getElementById("FPEmit2A").disabled = 1
             document.getElementById("FPEmit2B").disabled = 1
             document.getElementById("FPGain2").disabled = 1
        } else {
             document.getElementById("FP2Switch").setAttribute("style", "")
             document.getElementById("FPExcite2").disabled = 0
             document.getElementById("FPBase2").disabled = 0
             document.getElementById("FPEmit2A").disabled = 0
             document.getElementById("FPEmit2B").disabled = 0
             document.getElementById("FPGain2").disabled = 0
        }
        
        if (data.FP3.ON==1){
             document.getElementById("FP3Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             document.getElementById("FPExcite3").disabled = 1
             document.getElementById("FPBase3").disabled = 1
             document.getElementById("FPEmit3A").disabled = 1
             document.getElementById("FPEmit3B").disabled = 1
             document.getElementById("FPGain3").disabled = 1
        } else {
             document.getElementById("FP3Switch").setAttribute("style", "")
             document.getElementById("FPExcite3").disabled = 0
             document.getElementById("FPBase3").disabled = 0
             document.getElementById("FPEmit3A").disabled = 0
             document.getElementById("FPEmit3B").disabled = 0
             document.getElementById("FPGain3").disabled = 0
        }
        
        
      
        
         if (data.LASER650.ON==1){
             document.getElementById("LASER650Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LASER650Switch").setAttribute("style", "")
        }
        
         if (data.Thermostat.ON==1){
             document.getElementById("ThermostatSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("ThermostatSwitch").setAttribute("style", "")
        }
       
        if (data.Pump1.ON==1){
             document.getElementById("Pump1Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("Pump1Switch").setAttribute("style", "")
        }
        
        if (data.Pump2.ON==1){
             document.getElementById("Pump2Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("Pump2Switch").setAttribute("style", "")
        }
        
         if (data.Pump3.ON==1){
             document.getElementById("Pump3Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("Pump3Switch").setAttribute("style", "")
        }
        
         if (data.Pump4.ON==1){
             document.getElementById("Pump4Switch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("Pump4Switch").setAttribute("style", "")
        }
        
         if (data.Stir.ON==1){
             document.getElementById("StirSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("StirSwitch").setAttribute("style", "")
        }
        
         if (data.Light.ON==1){
             document.getElementById("LightSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("LightSwitch").setAttribute("style", "")
        }
        
         if (data.Custom.ON==1){
             document.getElementById("CustomSwitch").setAttribute("style", "border-style:inset;background-color:lightblue")
             
        } else {
             document.getElementById("CustomSwitch").setAttribute("style", "")
        }










        //Making stuff visible/invisible depending on LED version the user has.
        if (document.getElementById("FPRefresh").value != data.UIDevice){ //This means this code is only executed when we boot or when we are moving between devices.
         
       






          if (data.Version.LED == 1){

               const optionsLED1 = [
                    {value: "LEDA", text: "395/30"},
                    {value: "LEDB", text: "457/35"},
                    {value: "LEDC", text: "500/55"},
                    {value: "LEDD", text: "523/70"},
                    {value: "LEDE", text: "595/25"},
                    {value: "LEDF", text: "623/30"},
                    {value: "LEDG", text: "6500K"},
                    {value: "LASER650", text: "Laser"}
               ]
               let optionsHTML = "";
               optionsLED1.forEach(option => {
                    optionsHTML += `<option value="${option.value}">${option.text}</option>`;
               });
               document.getElementById('LightExcite1').innerHTML = optionsHTML;
               document.getElementById('FPExcite1').innerHTML = optionsHTML;
               document.getElementById('FPExcite2').innerHTML = optionsHTML;
               document.getElementById('FPExcite3').innerHTML = optionsHTML;

                    document.getElementById("LEDAContainer").style.display = "";
                    document.getElementById("LEDEContainer").style.display = "";
                    document.getElementById("LEDGContainer").style.display = "";
                    document.getElementById("LEDHContainer").style.display = "none";
                    document.getElementById("LEDIContainer").style.display = "none";
                    document.getElementById("LEDVContainer").style.display = "none";
          
          
          
          } else if (data.Version.LED == 2){
               const optionsLED2 = [
                    {value: "LEDB", text: "457/35"},
                    {value: "LEDC", text: "500/55"},
                    {value: "LEDD", text: "523/70"},
                    {value: "LEDI", text: "550/105"},
                    {value: "LEDH", text: "600/80"},
                    {value: "LEDF", text: "623/30"},
                    {value: "LEDV", text: "White"},
                    {value: "LASER650", text: "Laser"}
               ]
               let optionsHTML = "";
               optionsLED2.forEach(option => {
                    optionsHTML += `<option value="${option.value}">${option.text}</option>`;
               });
               document.getElementById('LightExcite1').innerHTML = optionsHTML;
               document.getElementById('FPExcite1').innerHTML = optionsHTML;
               document.getElementById('FPExcite2').innerHTML = optionsHTML;
               document.getElementById('FPExcite3').innerHTML = optionsHTML;

                    document.getElementById("LEDAContainer").style.display = "none";
                    document.getElementById("LEDEContainer").style.display = "none";
                    document.getElementById("LEDGContainer").style.display = "none";
                    document.getElementById("LEDHContainer").style.display = "";
                    document.getElementById("LEDIContainer").style.display = "";
                    document.getElementById("LEDVContainer").style.display = "";
          }
        }

















        
        
        if (data.presentDevices.M0 ==0) {
            document.getElementById("Device0").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M0'){
            document.getElementById("Device0").disabled= Boolean(0)
            document.getElementById("Device0").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device0").disabled= Boolean(0)
            document.getElementById("Device0").setAttribute("style", "")
        }
        
        
        
        if (data.presentDevices.M1 ==0) {
            document.getElementById("Device1").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M1'){
            document.getElementById("Device1").disabled= Boolean(0)
            document.getElementById("Device1").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device1").disabled= Boolean(0)
            document.getElementById("Device1").setAttribute("style", "")
        }
        
        
        
        if (data.presentDevices.M2 ==0) {
            document.getElementById("Device2").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M2'){
            document.getElementById("Device2").disabled= Boolean(0)
            document.getElementById("Device2").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device2").disabled= Boolean(0)
            document.getElementById("Device2").setAttribute("style", "")
        }
        
        
        
        if (data.presentDevices.M3 ==0) {
            document.getElementById("Device3").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M3'){
            document.getElementById("Device3").disabled= Boolean(0)
            document.getElementById("Device3").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device3").disabled= Boolean(0)
            document.getElementById("Device3").setAttribute("style", "")
        }
        
        
        
        if (data.presentDevices.M4 ==0) {
            document.getElementById("Device4").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M4'){
            document.getElementById("Device4").disabled= Boolean(0)
            document.getElementById("Device4").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device4").disabled= Boolean(0)
            document.getElementById("Device4").setAttribute("style", "")
        }
        
        
        
        if (data.presentDevices.M5 ==0) {
            document.getElementById("Device5").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M5'){
            document.getElementById("Device5").disabled= Boolean(0)
            document.getElementById("Device5").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device5").disabled= Boolean(0)
            document.getElementById("Device5").setAttribute("style", "")
        }
        
        
        if (data.presentDevices.M6 ==0) {
            document.getElementById("Device6").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M6'){
            document.getElementById("Device6").disabled= Boolean(0)
            document.getElementById("Device6").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device6").disabled= Boolean(0)
            document.getElementById("Device6").setAttribute("style", "")
        }
        
        if (data.presentDevices.M7 ==0) {
            document.getElementById("Device7").disabled= Boolean(1)
        
        } else if (data.UIDevice=='M7'){
            document.getElementById("Device7").disabled= Boolean(0)
            document.getElementById("Device7").setAttribute("style", "border-style:inset;background-color:LimeGreen")
             
        } else {
            document.getElementById("Device7").disabled= Boolean(0)
            document.getElementById("Device7").setAttribute("style", "")
        }
        
        
        
        
        
        var TurbidostatOn = Boolean(data.OD.ON); //True if we are regulating OD

        document.getElementById("Pump1Switch").disabled = (TurbidostatOn);
        document.getElementById("Pump1Set").disabled = (TurbidostatOn);
        document.getElementById("Pump2Switch").disabled = (TurbidostatOn);
        document.getElementById("Pump2Set").disabled = (TurbidostatOn);
         if (TurbidostatOn){
             document.getElementById("ODRegulate").setAttribute("style", "border-style:inset;background-color:lightblue")
        } else {
             document.getElementById("ODRegulate").setAttribute("style", "")
        }
        document.getElementById("ODRegulate").disabled = !Boolean(data.Experiment.ON)
        
        
         if (data.Zigzag.ON==1){
             document.getElementById("Zigzag").setAttribute("style", "border-style:inset;background-color:lightblue")
        } else {
             document.getElementById("Zigzag").setAttribute("style", "")
        }
        document.getElementById("Zigzag").disabled = !TurbidostatOn
             
               
       // Following if statement is for things that should be done only when changing betwix devices.
        if (document.getElementById("FPRefresh").value != data.UIDevice){
            document.getElementById("FPRefresh").value = data.UIDevice
            
            document.getElementById("FPExcite1").value = data.FP1.LED
            document.getElementById("FPBase1").value = data.FP1.BaseBand
            document.getElementById("FPEmit1A").value = data.FP1.Emit1Band
            document.getElementById("FPEmit1B").value = data.FP1.Emit2Band
            document.getElementById("FPGain1").value = data.FP1.Gain
            
            document.getElementById("FPExcite2").value = data.FP2.LED
            document.getElementById("FPBase2").value = data.FP2.BaseBand
            document.getElementById("FPEmit2A").value = data.FP2.Emit1Band
            document.getElementById("FPEmit2B").value = data.FP2.Emit2Band
            document.getElementById("FPGain2").value = data.FP2.Gain
            
            document.getElementById("FPExcite3").value = data.FP3.LED
            document.getElementById("FPBase3").value = data.FP3.BaseBand
            document.getElementById("FPEmit3A").value = data.FP3.Emit1Band
            document.getElementById("FPEmit3B").value = data.FP3.Emit2Band
            document.getElementById("FPGain3").value = data.FP3.Gain
        }
              
        renderFluorescence(data);  // fluorescence-assist panel (self-gates; safe every poll)

        // Now to draw the charts
        if( document.getElementById("GraphReplot").value!== data.time.record.length || document.getElementById("FPRefresh").innerHTML != data.UIDevice){
		  

          document.getElementById("GraphReplot").value=data.time.record.length;
          document.getElementById("FPRefresh").innerHTML = data.UIDevice

window._lastSysData = data;
          redrawCharts(data);

		  

        }
        

}






// ===================== uPlot charting (self-hosted; replaces Google Charts) =====================
// Charts are created once and updated in place via setData() each poll -- there is no
// per-cycle destroy/rebuild, so the old Google-Charts memory-leak workaround is gone. Colours
// come from a dataviz-validated categorical palette (blue/green/magenta); light and dark are
// both selected, not an auto-flip, and charts re-theme when the toggle flips.
var uplots = {};
var uplotKey = {};

function chartTheme(){
  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    dark:   dark,
    text:   dark ? '#e8e8e6' : '#0b0b0b',
    muted:  dark ? '#9a998f' : '#6b6a66',
    grid:   dark ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.07)',
    series: dark ? ['#3987e5','#008300','#d55181'] : ['#2a78d6','#008300','#e87ba4'],
    band:   dark ? 'rgba(57,135,229,0.20)' : 'rgba(42,120,214,0.13)'
  };
}

function roleColor(th, role){
  if (role === 'muted') return th.muted;
  return th.series[ role === 's1' ? 1 : role === 's2' ? 2 : 0 ];
}

function toHours(arr){
  var out = new Array(arr.length);
  for (var i = 0; i < arr.length; i++) out[i] = arr[i] / 3600.0;
  return out;
}

// seriesDefs: [{label, data, role:'s0'|'s1'|'s2'|'muted', width, dash, hidden}]
// band (optional): {series:[hiIdx, loIdx], fill}
function drawUplot(plotID, th, ylabel, x, seriesDefs, band){
  var el = document.getElementById('chart_div' + plotID);
  if (!el) return;

  var data = [x];
  for (var i = 0; i < seriesDefs.length; i++) data.push(seriesDefs[i].data);

  // Rebuild only when theme / series identity / band presence changes; otherwise setData.
  var key = th.dark + '|' + ylabel + '|' +
            seriesDefs.map(function(s){ return s.label; }).join(',') + '|' + (band ? 'B' : '');
  if (uplots[plotID] && uplotKey[plotID] === key){
    uplots[plotID].setData(data);
    return;
  }
  if (uplots[plotID]) uplots[plotID].destroy();

  var uSeries = [{}];
  for (var j = 0; j < seriesDefs.length; j++){
    var s = seriesDefs[j];
    uSeries.push({
      label:  s.label,
      stroke: s.hidden ? 'rgba(0,0,0,0)' : roleColor(th, s.role),
      width:  s.hidden ? 0 : (s.width || 2),
      dash:   s.dash ? [6, 4] : undefined,
      points: { show: false }
    });
  }

  var opts = {
    width:  Math.max(260, el.clientWidth || (el.parentNode ? el.parentNode.clientWidth : 0) || 600),
    height: 300,
    scales: { x: { time: false } },
    axes: [
      { stroke: th.muted, grid: { stroke: th.grid, width: 1 }, ticks: { stroke: th.grid, width: 1 }, font: '12px sans-serif' },
      { label: ylabel, stroke: th.muted, grid: { stroke: th.grid, width: 1 }, ticks: { stroke: th.grid, width: 1 }, font: '12px sans-serif', labelFont: '13px sans-serif' }
    ],
    series: uSeries,
    legend: { show: true }
    // uPlot's default cursor already draws a crosshair and shows live values in the legend
    // on hover -- the dataviz "hover layer". A custom cursor.focus needs extra DOM setup.
  };
  if (band) opts.bands = [{ series: band.series, fill: band.fill }];

  uplots[plotID] = new uPlot(opts, data, el);
  uplotKey[plotID] = key;
}

function drawFPChart(plotID, th, hours, fp, emit2ElId){
  var series = [{ label: 'Emission Band 1', data: fp.Emit1Record, role: 's0', width: 2 }];
  var e2 = document.getElementById(emit2ElId);
  if (e2 && e2.value !== 'OFF')
    series.push({ label: 'Emission Band 2', data: fp.Emit2Record, role: 's1', width: 1.5 });
  drawUplot(plotID, th, 'Normalised FP Emission', hours, series);
}

function redrawCharts(data){
  var th = chartTheme();
  var hours = toHours(data.time.record);

  // OD: median (the control value) with a spread band, the dark-corrected trace, and target.
  var od = data.OD.record;
  var spread = data.OD.spreadRecord || [];
  var hi = new Array(od.length), lo = new Array(od.length);
  for (var i = 0; i < od.length; i++){ var h = (spread[i] || 0) / 2; hi[i] = od[i] + h; lo[i] = od[i] - h; }
  // Order matters: band edges first (indices 1,2 for the fill), then the recessive traces,
  // and OD LAST so the blue line sits on top of the (usually-overlapping) dark-corrected one.
  drawUplot(1, th, 'Optical Density', hours, [
    { label: 'spread +', data: hi, hidden: true },
    { label: 'spread −', data: lo, hidden: true },
    { label: 'Target', data: data.OD.targetrecord, role: 'muted', dash: true, width: 1.5 },
    { label: 'OD (dark-corrected)', data: (data.OD.correctedRecord || od), role: 's1', width: 1.5 },
    { label: 'OD', data: od, role: 's0', width: 2 }
  ], { series: [1, 2], fill: th.band });

  // Temperature: culture / internal air / external air, plus the thermostat target.
  drawUplot(2, th, 'Temperature (°C)', hours, [
    { label: 'Culture', data: data.ThermometerIR.record, role: 's0', width: 2 },
    { label: 'Internal Air', data: data.ThermometerInternal.record, role: 's1', width: 1.5 },
    { label: 'External Air', data: data.ThermometerExternal.record, role: 's2', width: 1.5 },
    { label: 'Target', data: data.Thermostat.record, role: 'muted', dash: true, width: 1.5 }
  ]);

  drawUplot(3, th, 'Pump Rate', hours, [
    { label: 'Pump 1 (Input)', data: data.Pump1.record, role: 's0', width: 2 }
  ]);

  drawFPChart(4, th, hours, data.FP1, 'FPEmit1B');
  drawFPChart(5, th, hours, data.FP2, 'FPEmit2B');
  drawFPChart(6, th, hours, data.FP3, 'FPEmit3B');

  if (data.Zigzag.ON == 1){
    drawUplot(7, th, 'Growth Rate', hours, [
      { label: 'Growth Rate', data: data.GrowthRate.record, role: 's0', width: 2 }
    ]);
  }
}

// Re-theme all charts when the light/dark toggle flips (data unchanged, so the poll guard
// would otherwise skip the redraw).
if (window.MutationObserver){
  new MutationObserver(function(){
    for (var k in uplots){ if (uplots[k]) uplots[k].destroy(); }
    uplots = {}; uplotKey = {};
    if (window._lastSysData) redrawCharts(window._lastSysData);
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}


// ===================== Fluorescence assist: EEM heatmap + recommendation + apply =====================
var _BAND_WL = {nm410:410, nm440:440, nm470:470, nm510:510, nm550:550, nm583:583, nm620:620, nm670:670};
var _FLUOR_RAMP = ['#eef4fb','#cde2fb','#9ec5f4','#6da7ec','#3987e5','#1c5cab','#0d366b']; // sequential blue
function _fluorColor(frac){ frac = Math.max(0, Math.min(1, frac)); return _FLUOR_RAMP[Math.round(frac*(_FLUOR_RAMP.length-1))]; }

// Renders the scan result. Self-gates on a signature so it only rebuilds when the result changes
// (not every poll), which also keeps a user's "Applied…" status message from being clobbered.
function renderFluorescence(data){
  var fs = data.FluorescenceScan; if(!fs) return;
  var status = document.getElementById('FluorStatus'); if(!status) return;
  if(fs.status === 'running'){ status.textContent = 'Scanning… (~30–90 s)'; window._fluorSig = 'running'; return; }
  if(status.textContent.indexOf('Scanning') === 0) status.textContent = '';   // scan just finished
  var n = fs.matrix ? Object.keys(fs.matrix).length : 0;
  if(!n) return;
  var r = fs.recommendation;
  var sig = n + '|' + (r ? r.excite + r.emit1 + r.emit2 : 'none');
  if(window._fluorSig === sig) return;
  window._fluorSig = sig;

  var recEl = document.getElementById('FluorRec'), hmEl = document.getElementById('FluorHeatmap');
  if(r){
    window._fluorRec = r;
    recEl.innerHTML = '<b>Recommended:</b> excite <b>'+r.excite+'</b> ('+r.excite_nm+' nm), base '+r.base
      + ', emit1 <b>'+r.emit1+'</b> ('+r.emit1_nm+' nm), emit2 '+r.emit2+' ('+r.emit2_nm+' nm), gain '+r.gain
      + ' &nbsp; <button class="btn btn-sm btn-success fluorApply" data-fp="1">→ FP1</button>'
      + ' <button class="btn btn-sm btn-success fluorApply" data-fp="2">→ FP2</button>'
      + ' <button class="btn btn-sm btn-success fluorApply" data-fp="3">→ FP3</button>';
  } else {
    window._fluorRec = null;
    recEl.innerHTML = '<i>No clear fluorescence peak found — the sample may be non-fluorescent.</i>';
  }

  var bands = fs.bands || [], maxv = 0;
  for(var led in fs.matrix){ for(var i=0;i<bands.length;i++){ var v=fs.matrix[led][bands[i]]||0; if(v>maxv) maxv=v; } }
  if(maxv <= 0) maxv = 1;
  var rows = Object.keys(fs.matrix).sort(function(a,b){ return fs.matrix[a]._wl - fs.matrix[b]._wl; });
  var h = '<table style="border-collapse:collapse;font-size:12px"><tr><th style="padding:3px 6px;text-align:left">excite \\ emit (nm)</th>';
  for(var i=0;i<bands.length;i++) h += '<th style="padding:3px 6px">'+bands[i].replace('nm','')+'</th>';
  h += '</tr>';
  for(var ri=0;ri<rows.length;ri++){
    var led = rows[ri], row = fs.matrix[led];
    h += '<tr><td style="padding:3px 6px;white-space:nowrap"><b>'+led+'</b> '+row._wl+'</td>';
    for(var i=0;i<bands.length;i++){
      var b = bands[i], v = row[b]||0;
      var scatter = _BAND_WL[b] < row._wl + 20;                       // below the Stokes shift = scatter
      var isRec = r && led === r.excite && b === r.emit1;
      h += '<td style="padding:3px 6px;text-align:center;background:'+_fluorColor(v/maxv)+';color:'+((v/maxv)>0.5?'#fff':'#222')+';'
        + (scatter?'opacity:0.4;':'') + (isRec?'outline:2px solid #e34948;':'') + '">'+Math.round(v)+'</td>';
    }
    h += '</tr>';
  }
  hmEl.innerHTML = h + '</table>';
}

$(function(){
  $('#FluorScanQuick').click(function(){ $.ajax({type:'POST', url:'/FluorescenceScan/0/quick'}); document.getElementById('FluorStatus').textContent = 'Scanning… (~30–90 s)'; window._fluorSig = 'running'; });
  $('#FluorScanFull').click(function(){ $.ajax({type:'POST', url:'/FluorescenceScan/0/full'}); document.getElementById('FluorStatus').textContent = 'Scanning… (full sweep, minutes)'; window._fluorSig = 'running'; });
  // Apply fills the FP dropdowns; the user reviews and clicks that FP's Active button to enable.
  $(document).on('click', '.fluorApply', function(){
    var r = window._fluorRec; if(!r) return;
    var n = $(this).data('fp');
    $('#FPExcite'+n).val(r.excite); $('#FPBase'+n).val(r.base);
    $('#FPEmit'+n+'A').val(r.emit1); $('#FPEmit'+n+'B').val(r.emit2); $('#FPGain'+n).val(r.gain);
    document.getElementById('FluorStatus').textContent = 'Applied to FP'+n+' — review the FP'+n+' fields, then click its Active button to enable.';
  });
});
