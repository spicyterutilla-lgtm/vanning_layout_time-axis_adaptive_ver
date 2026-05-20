import pandas as pd
import uuid
import random
import datetime
import sys
from models import Item

TRUE_VALUES = {"1", "true", "yes", "y", "はい", "可", "可能", "○", "あり"}
FALSE_VALUES = {"0", "false", "no", "n", "いいえ", "不可", "×", "なし"}

class DataLoader:
    """
    様々なフォーマットの入力ファイルを吸収し、システムの内部モデル（Item）に変換するクラス
    """
    def __init__(self, mapping_config=None):
        self.input_profile = {}
        # 外部の列名をシステムの変数名にファジーマッチさせるための辞書
        self.mapping_config = mapping_config or {
            "name": ["資材名称", "品名", "Name", "名称", "アイテム"],
            "length": ["L", "長さ", "Length", "length_mm", "長さ(mm)"],
            "width": ["W", "幅", "Width", "width_mm", "幅(mm)"],
            "height": ["H", "高さ", "Height", "height_mm", "高さ(mm)"],
            "weight": ["重量", "Weight", "kg"],
            "creation": ["梱包日", "生産日", "available_date", "現場到着日", "積載可能日", "到着日"],
            "due": ["納期", "出荷日", "due_date"],
            "expiration": ["保管期限", "木箱期限", "storage_deadline", "expiration_date"],
            "priority": ["優先度", "priority"],
            "force_ship": ["強制出荷", "force_ship", "手動強制"],
            "allow_early_ship": ["前倒し可否", "前倒し許可", "allow_early_ship"],
            "stackable": ["段積み可否", "段積み可", "stackable"],
            "no_stack": ["段積み不可", "上積み不可", "no_stack"],
            "floor_only": ["床置き", "重量物下積み", "下積み指定", "floor_only"],
            "separation_group": ["分離グループ", "同梱不可グループ", "separation_group", "混載禁止グループ"]
        }

    def _normalize_column_name(self, value) -> str:
        return str(value).strip().lower().replace("　", " ").replace(" ", "").replace("_", "")

    def _find_column(self, df: pd.DataFrame, possible_names: list) -> str:
        """データフレームのカラムから、候補に合致する列を探す。完全一致を優先する。"""
        normalized_targets = [self._normalize_column_name(name) for name in possible_names]
        normalized_cols = {
            col: self._normalize_column_name(col)
            for col in df.columns
            if not str(col).startswith("Unnamed")
        }

        for col, normalized_col in normalized_cols.items():
            if normalized_col in normalized_targets:
                return col

        partial_targets = [target for target in normalized_targets if len(target) > 1]
        for col, normalized_col in normalized_cols.items():
            if any(target and target in normalized_col for target in partial_targets):
                return col
        return None

    def _parse_date(self, value, default=None):
        if pd.isna(value):
            return default
        return pd.to_datetime(value).date()

    def _parse_bool(self, value, default=False):
        if pd.isna(value):
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in TRUE_VALUES:
            return True
        if text in FALSE_VALUES:
            return False
        return default

    def _parse_group(self, value):
        if pd.isna(value):
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if text.lower() in FALSE_VALUES or text in {"-", "ー"}:
            return ""
        return text

    def load_from_excel(self, file_path: str, sheet_name: int = 0) -> list[Item]:
        print(f"ファイルの読み込みを開始します: {file_path}")
        
        # まずヘッダー無しで読み込んで、列名（L, W, Hなど）が書かれている行を自動探索する
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row_idx = 0
        
        for i in range(min(10, len(df_raw))): # 最初の10行を探索
            row_values = [self._normalize_column_name(val) for val in df_raw.iloc[i].values]
            required_matches = 0
            for key in ("name", "length", "width", "height"):
                normalized_names = [self._normalize_column_name(name) for name in self.mapping_config[key]]
                if any(name in row_values for name in normalized_names):
                    required_matches += 1
            if required_matches >= 3: # 名称、L、W、Hのうち3つ以上が見つかればヘッダー行と確定
                header_row_idx = i
                break
                
        # 見つけたヘッダー行を使って正しく読み込み直す
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row_idx)
        
        # 列名のマッピング
        name_col = self._find_column(df, self.mapping_config["name"])
        l_col = self._find_column(df, self.mapping_config["length"])
        w_col = self._find_column(df, self.mapping_config["width"])
        h_col = self._find_column(df, self.mapping_config["height"])
        weight_col = self._find_column(df, self.mapping_config["weight"])
        creation_col = self._find_column(df, self.mapping_config["creation"])
        due_col = self._find_column(df, self.mapping_config["due"])
        expiration_col = self._find_column(df, self.mapping_config["expiration"])
        priority_col = self._find_column(df, self.mapping_config["priority"])
        force_ship_col = self._find_column(df, self.mapping_config["force_ship"])
        allow_early_ship_col = self._find_column(df, self.mapping_config["allow_early_ship"])
        stackable_col = self._find_column(df, self.mapping_config["stackable"])
        no_stack_col = self._find_column(df, self.mapping_config["no_stack"])
        floor_only_col = self._find_column(df, self.mapping_config["floor_only"])
        separation_group_col = self._find_column(df, self.mapping_config["separation_group"])
        self.input_profile = {
            "sheet_name": str(sheet_name),
            "header_row": header_row_idx + 1,
            "total_rows": len(df),
            "generated_simulation": any(
                self._normalize_column_name(col) in {
                    self._normalize_column_name("仮定根拠"),
                    self._normalize_column_name("仮定重量階級"),
                    self._normalize_column_name("ケース階級"),
                }
                for col in df.columns
            ),
            "detected_columns": {
                "name": bool(name_col),
                "length": bool(l_col),
                "width": bool(w_col),
                "height": bool(h_col),
                "weight": bool(weight_col),
                "creation": bool(creation_col),
                "due": bool(due_col),
                "expiration": bool(expiration_col),
                "priority": bool(priority_col),
                "force_ship": bool(force_ship_col),
                "allow_early_ship": bool(allow_early_ship_col),
                "stackable": bool(stackable_col or no_stack_col),
                "floor_only": bool(floor_only_col),
                "separation_group": bool(separation_group_col),
            },
            "column_names": {
                "weight": str(weight_col) if weight_col else "",
                "creation": str(creation_col) if creation_col else "",
                "due": str(due_col) if due_col else "",
                "expiration": str(expiration_col) if expiration_col else "",
                "priority": str(priority_col) if priority_col else "",
                "allow_early_ship": str(allow_early_ship_col) if allow_early_ship_col else "",
                "stackable": str(stackable_col or no_stack_col) if (stackable_col or no_stack_col) else "",
                "floor_only": str(floor_only_col) if floor_only_col else "",
                "separation_group": str(separation_group_col) if separation_group_col else "",
            }
        }
        
        if not all([name_col, l_col, w_col, h_col]):
            raise ValueError("必要な列（名称、L、W、H）がExcelから見つかりませんでした。フォーマットを確認してください。")

        items = []
        today = datetime.date.today()
        
        for index, row in df.iterrows():
            if pd.isna(row[name_col]):
                continue
                
            try:
                l_val = float(row[l_col])
                w_val = float(row[w_col])
                h_val = float(row[h_col])
            except (ValueError, TypeError):
                # 「L」などの文字が再度出現した場合（途中のサブタイトル等）や空欄の場合はスキップ
                continue
                
            # 実務モード：Excelの値を厳密に使用
            item_name = str(row[name_col])
            is_wood = "燻蒸" in item_name or "木箱" in item_name
            
            # 重量: 列が存在すればそれを使用、なければ固定値1000kg（エラー回避）
            if weight_col and not pd.isna(row[weight_col]):
                simulated_weight = float(row[weight_col])
            else:
                simulated_weight = 1000.0
            
            # 時間軸: 列が存在すればそれを使用、なければ今日に設定
            creation_date = self._parse_date(row[creation_col], today) if creation_col else today
                
            due_date = self._parse_date(row[due_col], today + datetime.timedelta(days=7)) if due_col else today + datetime.timedelta(days=7)
            
            if expiration_col:
                expiration_date = self._parse_date(row[expiration_col], None)
            else:
                expiration_date = creation_date + datetime.timedelta(days=21) if is_wood else None

            priority = 50
            if priority_col and not pd.isna(row[priority_col]):
                priority = int(float(row[priority_col]))

            force_ship = self._parse_bool(row[force_ship_col], False) if force_ship_col else False
            allow_early_ship = self._parse_bool(row[allow_early_ship_col], True) if allow_early_ship_col else True
            
            stackable_val = True
            if stackable_col:
                stackable_val = self._parse_bool(row[stackable_col], True)
            elif no_stack_col:
                stackable_val = not self._parse_bool(row[no_stack_col], False)
            stackable = stackable_val
            
            floor_only = self._parse_bool(row[floor_only_col], False) if floor_only_col else False
            separation_group = self._parse_group(row[separation_group_col]) if separation_group_col else ""

            item = Item(
                id=str(uuid.uuid4())[:8],
                original_id=f"ROW-{index+1}",
                name=item_name,
                length=l_val,
                width=w_val,
                height=h_val,
                weight=simulated_weight,
                creation_date=creation_date,
                due_date=due_date,
                expiration_date=expiration_date,
                priority=priority,
                force_ship=force_ship,
                allow_early_ship=allow_early_ship,
                stackable=stackable,
                floor_only=floor_only,
                separation_group=separation_group
            )
            items.append(item)
            
        print(f"SUCCESS: {len(items)}件のデータをシステム共通フォーマットに変換しました。")
        return items

if __name__ == "__main__":
    # 動作確認用テスト
    loader = DataLoader()
    try:
        loaded_items = loader.load_from_excel("(抜粋)ケースリスト.xlsx", sheet_name=0)
        print("\n--- サンプルデータ（1件目） ---")
        item = loaded_items[0]
        print(f"品名: {item.name}")
        print(f"サイズ: {item.length} x {item.width} x {item.height} mm")
        print(f"重量: {item.weight} kg")
        print(f"梱包完了日: {item.creation_date}")
        print(f"納期: {item.due_date}")
        print(f"木箱期限: {item.expiration_date}")
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
