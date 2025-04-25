import pcbnew
import json
import os

# Load JSON netlist
with open("led_driver.json", "r") as f:
    data = json.load(f)

# Create a new board
board = pcbnew.BOARD()
unit = 1e6  # mm to nm
x_offset_mm, y_offset_mm = 50, 50
footprints = {}

# Add components and footprints
for comp in data["components"]:
    ref = comp["ref"]
    value = comp["value"]
    footprint_name = comp["footprint"]
    x_mm, y_mm = comp["position"]

    if not footprint_name.strip():
        continue

    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference(ref)
    footprint.SetValue(value)
    pos_x = int((x_mm * 1.5 + x_offset_mm) * unit)
    pos_y = int((y_mm * 1.5 + y_offset_mm) * unit)
    footprint.SetPosition(pcbnew.VECTOR2I(pos_x, pos_y))
    board.Add(footprint)
    footprints[ref] = footprint

    # Add 2 pads with spacing
    if value not in ("VCC", "GND"):
        spacing = pcbnew.FromMM(4.0)
        for i in range(2):
            pad = pcbnew.PAD(footprint)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.5), pcbnew.FromMM(1.5)))
            pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            pad.SetPadName(str(i + 1))
            pad.SetPosition(pcbnew.VECTOR2I(
                pos_x + (i * spacing) - spacing // 2,
                pos_y
            ))
            footprint.Add(pad)

# Draw board outline
outline = pcbnew.PCB_SHAPE(board)
outline.SetShape(pcbnew.SHAPE_T_RECT)
outline.SetLayer(pcbnew.Edge_Cuts)
outline.SetStart(pcbnew.VECTOR2I(int(0 * unit), int(0 * unit)))
outline.SetEnd(pcbnew.VECTOR2I(int(120 * unit), int(60 * unit)))
board.Add(outline)

# Net mapping
net_map = {}
for net in data["nets"]:
    net_name = net["net_name"]
    netinfo = pcbnew.NETINFO_ITEM(board, net_name)
    board.Add(netinfo)
    net_map[net_name] = netinfo

# Pad routing
for net in data["nets"]:
    net_name = net["net_name"]
    netinfo = net_map[net_name]
    nodes = net["nodes"]
    pads = []

    for ref in nodes:
        fp = footprints.get(ref)
        if fp:
            for pad in fp.Pads():
                pad.SetNet(netinfo)
                pads.append(pad)

    if len(pads) >= 2:
        for pad1, pad2 in zip(pads, pads[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pad1.GetPosition())
            track.SetEnd(pad2.GetPosition())
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(netinfo)
            board.Add(track)
            fp1 = pad1.GetParent()
            fp2 = pad2.GetParent()
            if isinstance(fp1, pcbnew.FOOTPRINT) and isinstance(fp2, pcbnew.FOOTPRINT):
                print(f"✅ Routed: {fp1.GetReference()} ↔ {fp2.GetReference()} on net {net_name}")
            else:
                print(f"✅ Routed pads on net {net_name}")

# ───────────────────────────────
# Add GND and VCC copper zones
# ───────────────────────────────
def add_zone(net_name):
    if net_name not in net_map:
        print(f"⚠️ Net {net_name} not found.")
        return

    net = net_map[net_name]
    footprint = footprints.get(net_name)
    if not footprint:
        print(f"⚠️ Footprint for reference {net_name} not found.")
        return

    zone_container = pcbnew.ZONE(board)
    zone_container.SetLayer(pcbnew.F_Cu)
    zone_container.SetNetCode(net.GetNet())
    zone_container.SetNet(net)
    zone_container.SetLocalClearance(pcbnew.FromMM(0.2))
    board.Add(zone_container)

    outline_points = [
        pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(1)),
        pcbnew.VECTOR2I(pcbnew.FromMM(119), pcbnew.FromMM(1)),
        pcbnew.VECTOR2I(pcbnew.FromMM(119), pcbnew.FromMM(59)),
        pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(59)),
    ]
    poly = zone_container.Outline()
    poly.NewOutline()
    for pt in outline_points:
        poly.Append(pt)

    zone_container.SetIsFilled(True)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    print(f"✅ Copper zone added for {net_name}")

add_zone("GND")
add_zone("VCC")

# Save PCB file
output_file = "led_driver_all_tracks.kicad_pcb"
pcbnew.SaveBoard(output_file, board)
print(f"✅ All pad-to-pad routed PCB saved to: {output_file}")

# ───────────────────────────────
# GERBER + DRILL FILE EXPORT
# ───────────────────────────────
gerber_dir = "gerber_output"
os.makedirs(gerber_dir, exist_ok=True)

plot_controller = pcbnew.PLOT_CONTROLLER(board)
plot_options = plot_controller.GetPlotOptions()

plot_options.SetOutputDirectory(gerber_dir)
plot_options.SetPlotFrameRef(False)
plot_options.SetAutoScale(False)
plot_options.SetUseGerberAttributes(True)
plot_options.SetScale(1.0)
plot_options.SetMirror(False)
plot_options.SetUseAuxOrigin(False)

layers = [
    (pcbnew.F_Cu, "F_Cu"),
    (pcbnew.B_Cu, "B_Cu"),
    (pcbnew.F_SilkS, "F_SilkS"),
    (pcbnew.B_SilkS, "B_SilkS"),
    (pcbnew.F_Mask, "F_Mask"),
    (pcbnew.B_Mask, "B_Mask"),
    (pcbnew.Edge_Cuts, "Edge_Cuts")
]

for layer_id, layer_name in layers:
    plot_controller.SetLayer(layer_id)
    plot_controller.OpenPlotfile(layer_name, pcbnew.PLOT_FORMAT_GERBER, layer_name)
    plot_controller.PlotLayer()
plot_controller.ClosePlot()

# Drill file
drill_writer = pcbnew.EXCELLON_WRITER(board)
drill_writer.SetOptions(False, False, pcbnew.VECTOR2I(0, 0), False)
drill_writer.SetFormat(True)
drill_writer.CreateDrillandMapFilesSet(gerber_dir, True, False)

print(f"✅ Gerber & drill files generated in: {gerber_dir}")
