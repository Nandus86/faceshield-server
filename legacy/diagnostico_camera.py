"""
Script de diagnóstico para identificar câmeras disponíveis no sistema.
Execute este script antes de usar a aplicação principal.
"""

import cv2
import sys

def test_camera(index):
    """Testa se uma câmera está disponível em um determinado índice."""
    print(f"\nTestando câmera no índice {index}...")
    
    try:
        cap = cv2.VideoCapture(index)
        
        if not cap.isOpened():
            print(f"  ❌ Câmera {index}: Não foi possível abrir")
            return False
        
        # Tenta ler um frame
        ret, frame = cap.read()
        
        if ret and frame is not None:
            height, width = frame.shape[:2]
            print(f"  ✅ Câmera {index}: DISPONÍVEL")
            print(f"     Resolução: {width}x{height}")
            cap.release()
            return True
        else:
            print(f"  ❌ Câmera {index}: Abriu mas não conseguiu capturar frames")
            cap.release()
            return False
            
    except Exception as e:
        print(f"  ❌ Câmera {index}: Erro - {e}")
        return False

def main():
    print("=" * 60)
    print("DIAGNÓSTICO DE CÂMERAS - Sistema de Reconhecimento Facial")
    print("=" * 60)
    
    print("\nVerificando câmeras disponíveis (índices 0-5)...")
    
    available_cameras = []
    
    for i in range(6):
        if test_camera(i):
            available_cameras.append(i)
    
    print("\n" + "=" * 60)
    print("RESULTADO DO DIAGNÓSTICO")
    print("=" * 60)
    
    if available_cameras:
        print(f"\n✅ {len(available_cameras)} câmera(s) encontrada(s):")
        for idx in available_cameras:
            print(f"   - Índice {idx}")
        
        print(f"\n📝 INSTRUÇÕES:")
        print(f"   1. Abra a aplicação principal (python main.py)")
        print(f"   2. Clique em 'Configurações'")
        print(f"   3. Configure o índice da câmera para: {available_cameras[0]}")
        print(f"   4. Clique em 'Testar Câmera' para confirmar")
        print(f"   5. Clique em 'Salvar Configurações'")
    else:
        print("\n❌ NENHUMA CÂMERA ENCONTRADA!")
        print("\nPossíveis causas:")
        print("   1. Nenhuma webcam está conectada")
        print("   2. Outra aplicação está usando a câmera")
        print("   3. Drivers da câmera não estão instalados")
        print("   4. Permissões de câmera bloqueadas pelo Windows")
        
        print("\n🔧 Soluções:")
        print("   1. Verifique se a câmera está conectada")
        print("   2. Feche programas como Teams, Zoom, Skype")
        print("   3. Reinicie o computador")
        print("   4. Verifique as permissões de câmera no Windows:")
        print("      Configurações → Privacidade → Câmera")
    
    print("\n" + "=" * 60)
    input("\nPressione ENTER para sair...")

if __name__ == "__main__":
    main()
