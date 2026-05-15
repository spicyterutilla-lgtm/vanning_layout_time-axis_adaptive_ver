import pandas as pd
import uuid
import random
import datetime
import sys
from models import Item

class DataLoader:
    """
    様々なフォーマットの入力ファイルを吸収し、システムの内部モデル（Item）に変換するクラス
    """
    def __init__(self, mapping_config=None):
        # 外部の列名をシステムの変数名にファジーマッチさせるための辞書
        self.mapping_config = mapping_config or {
            "name": ["資材名称", "品名", "Name", "名称", "アイテム"],
            "length": ["L", "長さ", "Length"],
            "width": ["W", "幅", "Width"],
            "height": ["H", "高さ", "Height"],
            "weight": ["重量", "Weight", "kg"],
            "creation": ["梱包日", "生産日"],
            "due": ["納期", "出荷日"]
        }

    def _find_column(self, df: pd.DataFrame, possible_names: list) -> str:
        """データフレームのカラムから、マッピング辞書の候補に合致するものを探す"""
        for col in df.columns:
            if any(name.lower() in str(col).lower() for name in possible_names):
                return col
        return None

    def load_from_excel(self, file_path: str, sheet_name: int = 0) -> list[Item]:
        print(f"ファイルの読み込みを開始します: {file_path}")
        
        # まずヘッダー無しで読み込んで、列名（L, W, Hなど）が書かれている行を自動探索する
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row_idx = 0
        
        for i in range(min(10, len(df_raw))): # 最初の10行を探索
            row_values = [str(val).lower() for val in df_raw.iloc[i].values]
            match_count = 0
            for possible_names in self.mapping_config.values():
                if any(name.lower() in row_values for name in possible_names):
                    match_count += 1
            if match_count >= 3: # 名称、L、W、Hのうち3つ以上が見つかればヘッダー行と確定
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
            if creation_col and not pd.isna(row[creation_col]):
                creation_date = pd.to_datetime(row[creation_col]).date()
            else:
                creation_date = today
                
            if due_col and not pd.isna(row[due_col]):
                due_date = pd.to_datetime(row[due_col]).date()
            else:
                due_date = today + datetime.timedelta(days=7)
            
            expiration_date = creation_date + datetime.timedelta(days=21) if is_wood else None

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
                expiration_date=expiration_date
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
