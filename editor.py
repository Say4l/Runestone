#!/usr/bin/env python3
import sys
import os
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QGraphicsScene, QGraphicsView,
    QListWidget, QListWidgetItem, QWidget, QPushButton, QLabel, QComboBox,
    QHBoxLayout, QVBoxLayout, QToolBar, QAction, QSpinBox, QMessageBox
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QBrush
from PyQt5.QtCore import Qt, QRectF, QPointF

# Constants for default map properties
DEFAULT_MAP_COLS = 20
DEFAULT_MAP_ROWS = 15
DEFAULT_TILE_SIZE = 16

class MapScene(QGraphicsScene):
    """
    This QGraphicsScene subclass displays the map grid and the placed tiles.
    It also handles mouse clicks for tile placement or collision toggling.
    """
    def __init__(self, editor):
        super().__init__()
        self.editor = editor  # reference to the main editor (to access current tool, layer, etc.)
        self.setBackgroundBrush(Qt.darkGray)
    
    def drawBackground(self, painter, rect):
        # Draw grid lines
        tile_size = self.editor.tile_size
        pen = QPen(QColor(80, 80, 80))
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % tile_size)
        top = int(rect.top()) - (int(rect.top()) % tile_size)
        # vertical lines
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += tile_size
        # horizontal lines
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += tile_size

        # Draw collision overlay (semi-transparent red)
        if self.editor.show_collision:
            collision = self.editor.collision
            for row in range(self.editor.map_rows):
                for col in range(self.editor.map_cols):
                    if collision[row][col]:
                        cell_rect = QRectF(col*tile_size, row*tile_size, tile_size, tile_size)
                        painter.fillRect(cell_rect, QColor(0, 0, 0, 0))
    
    def mousePressEvent(self, event):
        # Determine the grid cell that was clicked
        pos = event.scenePos()
        col = int(pos.x() // self.editor.tile_size)
        row = int(pos.y() // self.editor.tile_size)
        if col < 0 or row < 0 or col >= self.editor.map_cols or row >= self.editor.map_rows:
            return

        # Two modes: tile placement or collision toggle
        if self.editor.current_mode == "tile":
            current_tile = self.editor.current_tile_index
            if current_tile is None:
                return  # no tile selected
            # Place the tile in the current layer at (row, col)
            layer = self.editor.current_layer
            self.editor.layers[layer][row][col] = current_tile
        elif self.editor.current_mode == "collision":
            # Toggle collision flag at this cell
            self.editor.collision[row][col] = not self.editor.collision[row][col]
        # Redraw the scene
        self.editor.updateScene()
        super().mousePressEvent(event)


class LevelEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Level Editor")
        self.resize(1200, 800)
        self.tile_size = DEFAULT_TILE_SIZE
        self.map_cols = DEFAULT_MAP_COLS
        self.map_rows = DEFAULT_MAP_ROWS

        # Data structures for map layers and collision:
        # layers is a dict mapping layer name to a 2D grid (list of lists) of tile indices (or None)
        self.layers = {}
        self.addLayer("Base")
        self.current_layer = "Base"  # currently selected layer
        # Collision grid: same dimensions as map; each cell is True/False.
        self.collision = [[False for _ in range(self.map_cols)] for _ in range(self.map_rows)]
        self.show_collision = True

        # Tileset related
        self.tileset = None        # QPixmap of the full tileset image
        self.tiles = []            # List of QPixmap for each individual tile (sliced from the tileset)
        self.tiles_per_row = 0
        self.current_tile_index = None  # index into self.tiles

        # Editor mode: "tile" for placing tiles, "collision" for toggling collision
        self.current_mode = "tile"

        self.initUI()

    def initUI(self):
        # Create toolbar actions
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        loadTilesetAction = QAction("Load Tileset", self)
        loadTilesetAction.triggered.connect(self.loadTileset)
        toolbar.addAction(loadTilesetAction)

        saveMapAction = QAction("Save Map", self)
        saveMapAction.triggered.connect(self.saveMap)
        toolbar.addAction(saveMapAction)

        # Mode toggle buttons
        self.tileModeButton = QPushButton("Tile Mode")
        self.tileModeButton.setCheckable(True)
        self.tileModeButton.setChecked(True)
        self.tileModeButton.clicked.connect(lambda: self.setMode("tile"))
        toolbar.addWidget(self.tileModeButton)

        self.collisionModeButton = QPushButton("Collision Mode")
        self.collisionModeButton.setCheckable(True)
        self.collisionModeButton.clicked.connect(lambda: self.setMode("collision"))
        toolbar.addWidget(self.collisionModeButton)

        # Layer selection
        toolbar.addWidget(QLabel("Layer:"))
        self.layerCombo = QComboBox()
        self.layerCombo.addItems(list(self.layers.keys()))
        self.layerCombo.currentTextChanged.connect(self.changeLayer)
        toolbar.addWidget(self.layerCombo)

        addLayerButton = QPushButton("Add Layer")
        addLayerButton.clicked.connect(self.addLayerDialog)
        toolbar.addWidget(addLayerButton)

        # Create the main widget and layout
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Left: Graphics view for map editing
        self.scene = MapScene(self)
        self.scene.setSceneRect(0, 0, self.map_cols*self.tile_size, self.map_rows*self.tile_size)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        main_layout.addWidget(self.view, stretch=3)

        # Right: Tile palette and controls
        palette_layout = QVBoxLayout()
        palette_label = QLabel("Tile Palette")
        palette_layout.addWidget(palette_label)
        self.tileList = QListWidget()
        self.tileList.setViewMode(QListWidget.IconMode)
        self.tileList.setIconSize(QPixmap(self.tile_size, self.tile_size).size())
        self.tileList.setResizeMode(QListWidget.Adjust)
        self.tileList.itemClicked.connect(self.selectTile)
        palette_layout.addWidget(self.tileList, stretch=1)

        # Additional controls (optional: show collision toggle)
        toggleCollisionVisibility = QPushButton("Toggle Collision Overlay")
        toggleCollisionVisibility.clicked.connect(self.toggleCollisionVisibility)
        palette_layout.addWidget(toggleCollisionVisibility)

        # Spacer
        palette_layout.addStretch()
        main_layout.addLayout(palette_layout, stretch=1)

        self.updateScene()

    def updateScene(self):
        # Clear all items and re-draw all layers.
        self.scene.clear()

        painter = QPainter()
        # Draw each layer’s tiles in order.
        # (Assuming layer order is the order in self.layers keys.)
        for layer_name, grid in self.layers.items():
            for row in range(self.map_rows):
                for col in range(self.map_cols):
                    tile_index = grid[row][col]
                    if tile_index is not None and self.tiles:
                        tile_pix = self.tiles[tile_index]
                        if tile_pix:
                            self.scene.addPixmap(tile_pix).setPos(col*self.tile_size, row*self.tile_size)
        # (The grid lines and collision overlays are drawn in drawBackground.)
        self.scene.update()

    def setMode(self, mode):
        self.current_mode = mode
        if mode == "tile":
            self.tileModeButton.setChecked(True)
            self.collisionModeButton.setChecked(False)
        else:
            self.tileModeButton.setChecked(False)
            self.collisionModeButton.setChecked(True)

    def selectTile(self, item):
        # The item's data holds the tile index.
        self.current_tile_index = item.data(Qt.UserRole)
        # Automatically switch to tile placement mode.
        self.setMode("tile")

    def loadTileset(self):
        # Load a tileset image from file.
        filename, _ = QFileDialog.getOpenFileName(self, "Load Tileset", "", "Image Files (*.png *.jpg *.bmp)")
        if not filename:
            return
        self.tileset = QPixmap(filename)
        if self.tileset.isNull():
            QMessageBox.warning(self, "Error", "Could not load image!")
            return

        # Ask for the tile size (or use default)
        ok = True
        # For simplicity, we use the default tile size here.
        # (You can also implement a dialog to ask for the tile size.)
        self.tile_size = DEFAULT_TILE_SIZE

        # Slice the tileset image into tiles
        self.tiles.clear()
        self.tileList.clear()
        tileset_width = self.tileset.width()
        tileset_height = self.tileset.height()
        self.tiles_per_row = tileset_width // self.tile_size
        for y in range(0, tileset_height, self.tile_size):
            for x in range(0, tileset_width, self.tile_size):
                rect = QRectF(x, y, self.tile_size, self.tile_size)
                tile = self.tileset.copy(x, y, self.tile_size, self.tile_size)
                self.tiles.append(tile)
                # Add to palette list with icon (transparency is preserved automatically)
                item = QListWidgetItem(QIcon(tile), "")
                item.setData(Qt.UserRole, len(self.tiles)-1)
                self.tileList.addItem(item)

    def addLayer(self, name):
        # Create an empty grid for the new layer (all cells start as None)
        grid = [[None for _ in range(self.map_cols)] for _ in range(self.map_rows)]
        self.layers[name] = grid

    def addLayerDialog(self):
        # For simplicity, here we just auto-name a new layer.
        new_layer_name = f"Layer {len(self.layers)+1}"
        self.addLayer(new_layer_name)
        self.layerCombo.addItem(new_layer_name)
        self.layerCombo.setCurrentText(new_layer_name)
        self.current_layer = new_layer_name
        self.updateScene()

    def changeLayer(self, layer_name):
        self.current_layer = layer_name

    def toggleCollisionVisibility(self):
        self.show_collision = not self.show_collision
        self.scene.update()

    def saveMap(self):
        # Gather all data into a dictionary.
        map_data = {
            "tile_size": self.tile_size,
            "map_cols": self.map_cols,
            "map_rows": self.map_rows,
            "tileset": "",  # we'll store the tileset file path if available
            "layers": {},
            "collision": self.collision,
        }
        # For each layer, save the grid.
        for layer_name, grid in self.layers.items():
            map_data["layers"][layer_name] = grid

        # If a tileset has been loaded from a file, store its path.
        # (In a real editor you might copy the tileset to your game assets folder.)
        if self.tileset:
            # For this example, we assume the tileset file is in the same folder
            # as the map file, so we just store the basename.
            # In a more robust solution, you might store an absolute path or a relative path.
            map_data["tileset"] = os.path.basename(self.tileset_file) if hasattr(self, 'tileset_file') else ""

        # Ask user for filename to save.
        filename, _ = QFileDialog.getSaveFileName(self, "Save Map", "", "JSON Files (*.json)")
        if not filename:
            return
        try:
            with open(filename, "w") as f:
                json.dump(map_data, f, indent=4)
            QMessageBox.information(self, "Saved", f"Map saved to {filename}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save map: {e}")

    def closeEvent(self, event):
        # Confirm before closing if necessary.
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = LevelEditor()
    editor.show()
    sys.exit(app.exec_())
